import hashlib
from collections import OrderedDict
from array import array
from bisect import bisect_left
import sys
import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from .document_parser import PARSER_VERSION, timestamp

SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 name TEXT NOT NULL, current_revision TEXT NOT NULL, status TEXT NOT NULL,
 phase TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, error TEXT, warnings TEXT NOT NULL DEFAULT '[]',
 model_digest TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(project_id,name));
CREATE TABLE IF NOT EXISTS document_revisions(
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, content_hash TEXT NOT NULL, original BLOB NOT NULL,
 imported_at TEXT NOT NULL, filesystem_modified_at TEXT, revision_time TEXT NOT NULL, revision_basis TEXT NOT NULL,
 units TEXT, parser_version TEXT, UNIQUE(document_id,version));
CREATE TABLE IF NOT EXISTS document_chunks(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 revision_id TEXT NOT NULL REFERENCES document_revisions(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, text TEXT NOT NULL, text_hash TEXT NOT NULL, locator TEXT NOT NULL,
 UNIQUE(revision_id,ordinal));
CREATE INDEX IF NOT EXISTS chunks_scope ON document_chunks(project_id,revision_id);
CREATE TABLE IF NOT EXISTS document_embeddings(
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 text_hash TEXT NOT NULL, model TEXT NOT NULL, digest TEXT NOT NULL,
 dimensions INTEGER NOT NULL, vector BLOB NOT NULL,
 PRIMARY KEY(project_id,text_hash,model,digest));
CREATE TABLE IF NOT EXISTS document_facts(
 chunk_id TEXT NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 subject TEXT NOT NULL, value TEXT NOT NULL, scope TEXT NOT NULL);
'''
SOURCE_CACHE_BYTES = 32 * 1024 * 1024


def _now(): return datetime.now(timezone.utc).isoformat()


def _retained_bytes(value, seen=None):
    seen = seen if seen is not None else set()
    if id(value) in seen: return 0
    seen.add(id(value)); size = sys.getsizeof(value)
    if isinstance(value, dict): return size + sum(_retained_bytes(k, seen) + _retained_bytes(v, seen) for k,v in value.items())
    if isinstance(value, (list, tuple)): return size + sum(_retained_bytes(v, seen) for v in value)
    return size


def _error(message,status=409):
    from .store import DomainError
    return DomainError(message,status)


class DocumentStore:
    def init_documents(self):
        self._source_cache=OrderedDict()
        self._source_cache_bytes=0
        self.db.executescript(SCHEMA)
        # Cache validity follows the stored source, including changes through
        # another SQLite connection. Existing databases migrate in place.
        if 'source_epoch' not in {r[1] for r in self.db.execute('PRAGMA table_info(document_revisions)')}:
            self.db.execute('ALTER TABLE document_revisions ADD COLUMN source_epoch INTEGER NOT NULL DEFAULT 0')
        self.db.executescript('''CREATE TRIGGER IF NOT EXISTS revision_source_changed
            AFTER UPDATE OF units ON document_revisions BEGIN
            UPDATE document_revisions SET source_epoch=OLD.source_epoch+1 WHERE id=NEW.id;
            END;''')
        try:
            self.db.execute('CREATE VIRTUAL TABLE temp.pm_fts_probe USING fts5(text)')
            self.db.execute('DROP TABLE temp.pm_fts_probe')
            self.fts5_supported=True
        except Exception: self.fts5_supported=False
        with self.db:
            self.db.execute("UPDATE documents SET status='queued',phase='recovering' WHERE status IN ('parsing','indexing_embeddings')")

    def fts_table(self, project_id):
        # Only a server-derived hex identifier enters SQL; never a user filename or path.
        return 'project_fts_'+hashlib.sha256(project_id.encode()).hexdigest()[:32]

    def ensure_fts(self, project_id):
        self.project(project_id)
        if not self.fts5_supported: raise _error('This Python SQLite build lacks FTS5',503)
        table=self.fts_table(project_id)
        self.db.execute(f'CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING fts5(chunk_id UNINDEXED,document_id UNINDEXED,text,heading, tokenize="unicode61")')
        return table

    def document(self, project_id, document_id):
        self.project(project_id)
        row=self.db.execute('SELECT * FROM documents WHERE id=? AND project_id=?',(document_id,project_id)).fetchone()
        if not row: raise _error('Document not found in this project',404)
        return dict(row)

    def list_documents(self, project_id):
        self.project(project_id)
        rows=self.db.execute('''SELECT d.*,r.version,r.content_hash,r.revision_time,r.revision_basis,r.imported_at,
        (SELECT COUNT(*) FROM document_chunks c WHERE c.revision_id=d.current_revision) AS chunk_count
        FROM documents d JOIN document_revisions r ON r.id=d.current_revision WHERE d.project_id=? ORDER BY d.name''',(project_id,)).fetchall()
        return [{**dict(r),'warnings':json.loads(r['warnings'])} for r in rows]

    def upload_document(self, project_id, name, data, filesystem_modified=None):
        self.project(project_id)
        digest=hashlib.sha256(data).hexdigest();now=_now()
        existing=self.db.execute('SELECT * FROM documents WHERE project_id=? AND name=?',(project_id,name)).fetchone()
        if existing:
            revision=self.db.execute('SELECT * FROM document_revisions WHERE id=?',(existing['current_revision'],)).fetchone()
            if revision['content_hash']==digest: return {'document_id':existing['id'],'revision_id':revision['id'],'unchanged':True}
        elif self.db.execute('SELECT COUNT(*) FROM documents WHERE project_id=?',(project_id,)).fetchone()[0]>=50:
            raise _error('Initial project limit is 50 documents',422)
        document_id=existing['id'] if existing else str(uuid4());revision_id=str(uuid4())
        version=self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM document_revisions WHERE document_id=?',(document_id,)).fetchone()[0]
        modified=timestamp(filesystem_modified)
        with self.db:
            self.ensure_fts(project_id)
            if existing:
                self.db.execute("UPDATE documents SET current_revision=?,status='queued',phase='queued',progress=0,error=NULL,warnings='[]',model_digest=NULL,updated_at=? WHERE id=?",(revision_id,now,document_id))
                self.db.execute(f'DELETE FROM {self.fts_table(project_id)} WHERE document_id=?',(document_id,))
            else:
                self.db.execute("INSERT INTO documents(id,project_id,name,current_revision,status,phase,created_at,updated_at) VALUES(?,?,?,?,'queued','queued',?,?)",(document_id,project_id,name,revision_id,now,now))
            self.db.execute('''INSERT INTO document_revisions(id,document_id,version,content_hash,original,imported_at,filesystem_modified_at,revision_time,revision_basis)
            VALUES(?,?,?,?,?,?,?,?,?)''',(revision_id,document_id,version,digest,data,now,modified,modified or now,'filesystem' if modified else 'import'))
            self.bump()
        return {'document_id':document_id,'revision_id':revision_id,'unchanged':False}

    def next_document_job(self):
        row=self.db.execute("SELECT d.project_id,d.id AS document_id,d.name,d.current_revision AS revision_id,r.* FROM documents d JOIN document_revisions r ON r.id=d.current_revision WHERE d.status='queued' ORDER BY d.updated_at LIMIT 1").fetchone()
        return dict(row) if row else None

    def document_job_current(self, document_id, revision_id):
        return self.db.execute('SELECT 1 FROM documents WHERE id=? AND current_revision=?',(document_id,revision_id)).fetchone() is not None

    def document_state(self, document_id, revision_id, status, phase, progress, error=None):
        self.db.execute('UPDATE documents SET status=?,phase=?,progress=?,error=?,updated_at=? WHERE id=? AND current_revision=?',
                        (status,phase,progress,error,_now(),document_id,revision_id));self.bump()

    def commit_parsed(self, project_id, document_id, revision_id, parsed):
        if not self.document_job_current(document_id,revision_id): return
        other=self.db.execute('SELECT COUNT(*) FROM document_chunks c JOIN documents d ON d.current_revision=c.revision_id WHERE d.project_id=? AND d.id!=?',(project_id,document_id)).fetchone()[0]
        if other+len(parsed['chunks'])>20000: raise _error('Project exceeds 20,000 current chunks',422)
        revision=self.db.execute('SELECT * FROM document_revisions WHERE id=?',(revision_id,)).fetchone()
        internal=timestamp(parsed['internal_modified_at'])
        basis='internal' if internal else 'filesystem' if revision['filesystem_modified_at'] else 'import'
        revision_time=internal or revision['filesystem_modified_at'] or revision['imported_at']
        table=self.ensure_fts(project_id)
        # Existing parsed revisions are immutable; retries reuse their chunks and citation IDs.
        if revision['units'] is not None: return
        with self.db:
            self.db.execute('UPDATE document_revisions SET units=?,parser_version=?,revision_time=?,revision_basis=? WHERE id=?',
                (json.dumps(parsed['units'],ensure_ascii=False),PARSER_VERSION,revision_time,basis,revision_id))
            self.db.execute(f'DELETE FROM {table} WHERE document_id=?',(document_id,))
            for ordinal,chunk in enumerate(parsed['chunks']):
                locator=json.dumps(chunk['locator'],sort_keys=True,ensure_ascii=False)
                chunk_id='cite_'+hashlib.sha256((project_id+':'+revision_id+':'+str(ordinal)+':'+chunk['text_hash']+':'+locator).encode()).hexdigest()
                self.db.execute('INSERT INTO document_chunks VALUES(?,?,?,?,?,?,?,?)',
                    (chunk_id,project_id,document_id,revision_id,ordinal,chunk['text'],chunk['text_hash'],locator))
                self.db.execute(f'INSERT INTO {table}(chunk_id,document_id,text,heading) VALUES(?,?,?,?)',
                    (chunk_id,document_id,chunk['text'],chunk['locator'].get('heading','')))
                self._facts(project_id,chunk_id,chunk['text'],chunk['locator'].get('heading',''))
            self.db.execute("UPDATE documents SET status='lexical_ready',phase='lexical ready',progress=.5,warnings=?,error=NULL WHERE id=? AND current_revision=?",(json.dumps(parsed['warnings']),document_id,revision_id))
            self.bump()

    def _facts(self, project_id, chunk_id, text, scope):
        for line in text.splitlines()[:200]:
            match=re.fullmatch(r'\s*([\w][\w ._/-]{2,79})\s*[:=]\s*(.{1,300}?)\s*',line)
            if not match: match=re.fullmatch(r'\s*([\w][\w ._/-]{2,79})\s+(?:is|will be)\s+(.{1,300}?)\s*[.]?\s*',line,re.I)
            if match:
                subject=re.sub(r'[_\s]+',' ',match[1].casefold()).strip()
                if subject in {'updated at','last updated','modified at','last modified','revision date','x-revision-date','x-last-updated'}: continue
                self.db.execute('INSERT INTO document_facts VALUES(?,?,?,?,?)',(chunk_id,project_id,subject,match[2].strip(),scope.casefold()))

    def revision_chunks(self, project_id, revision_id):
        return [dict(r) for r in self.db.execute('SELECT * FROM document_chunks WHERE project_id=? AND revision_id=? ORDER BY ordinal',(project_id,revision_id))]

    def embedding_cache(self, project_id, model, digest, hashes):
        if not hashes: return {}
        placeholders=','.join('?' for _ in hashes)
        return {r['text_hash']:dict(r) for r in self.db.execute(f'SELECT * FROM document_embeddings WHERE project_id=? AND model=? AND digest=? AND text_hash IN ({placeholders})',(project_id,model,digest,*hashes))}

    def save_embeddings(self, project_id, model, digest, vectors):
        self.project(project_id)
        with self.db:
            for text_hash,dimensions,vector in vectors:
                self.db.execute('INSERT OR IGNORE INTO document_embeddings VALUES(?,?,?,?,?,?)',(project_id,text_hash,model,digest,dimensions,vector))
            self.bump()

    def indexed_document(self, document_id, revision_id, digest):
        self.db.execute("UPDATE documents SET status='ready',phase='ready',progress=1,error=NULL,model_digest=? WHERE id=? AND current_revision=?",(digest,document_id,revision_id));self.bump()

    def reindex_document(self, project_id, document_id):
        d=self.document(project_id,document_id)
        self.document_state(document_id,d['current_revision'],'queued','queued',0)

    def delete_document(self, project_id, document_id):
        self.document(project_id,document_id)
        self._source_cache.clear()
        self._source_cache_bytes=0
        with self.db:
            table=self.ensure_fts(project_id)
            self.db.execute(f'DELETE FROM {table} WHERE document_id=?',(document_id,))
            self.db.execute('DELETE FROM documents WHERE id=? AND project_id=?',(document_id,project_id))
            # Remove vectors only when no retained revision in this project references them.
            self.db.execute('DELETE FROM document_embeddings WHERE project_id=? AND text_hash NOT IN (SELECT text_hash FROM document_chunks WHERE project_id=?)',(project_id,project_id))
            self.bump()

    def drop_project_knowledge(self, project_id):
        self._source_cache.clear()
        self._source_cache_bytes=0
        self.db.execute(f'DROP TABLE IF EXISTS {self.fts_table(project_id)}')

    def lexical_candidates(self, project_id, query):
        self.project(project_id)
        table=self.ensure_fts(project_id)
        tokens=re.findall(r'\w+',query,re.UNICODE)[:20]
        if not tokens: raise _error('Search requires at least one word',422)
        expression=' OR '.join('"'+t+'"' for t in tokens)
        return [dict(r) for r in self.db.execute(f'''SELECT c.*,r.revision_time,bm25({table}) AS lexical_score
            FROM {table} JOIN document_chunks c ON c.id={table}.chunk_id
            JOIN documents d ON d.current_revision=c.revision_id JOIN document_revisions r ON r.id=c.revision_id
            WHERE {table} MATCH ? AND c.project_id=? ORDER BY lexical_score LIMIT 60''',(expression,project_id))]

    def semantic_rows(self, project_id, model, digest):
        self.project(project_id)
        return [dict(r) for r in self.db.execute('''SELECT c.*,r.revision_time,e.vector,e.dimensions FROM document_chunks c
        JOIN documents d ON d.current_revision=c.revision_id JOIN document_revisions r ON r.id=c.revision_id
        JOIN document_embeddings e ON e.project_id=c.project_id AND e.text_hash=c.text_hash
        WHERE c.project_id=? AND e.model=? AND e.digest=?''',(project_id,model,digest))]

    def citation(self, project_id, chunk_id):
        self.project(project_id)
        row=self.db.execute('''SELECT c.*,r.version,r.content_hash,r.revision_time,r.revision_basis,r.source_epoch,d.name,d.current_revision
        FROM document_chunks c JOIN document_revisions r ON r.id=c.revision_id JOIN documents d ON d.id=c.document_id
        WHERE c.id=? AND c.project_id=? AND d.project_id=?''',(chunk_id,project_id,project_id)).fetchone()
        if not row: raise _error('Citation does not exist in this project',404)
        try:
            locator=json.loads(row['locator'])
            revision_id=row['revision_id']
            cached=self._source_cache.get(revision_id)
            if cached is None or cached['epoch']!=row['source_epoch']:
                if cached is not None:
                    self._source_cache_bytes-=cached['bytes']
                    del self._source_cache[revision_id]
                units=json.loads(self.db.execute('SELECT units FROM document_revisions WHERE id=?',(revision_id,)).fetchone()[0])
                # Packed newline indices avoid scanning/allocating the complete
                # source prefix on each status broadcast or citation lookup.
                lines=[array('I',(m.start() for m in re.finditer('\n',entry['text']))) if entry['locator']['kind']=='text' else None for entry in units]
                cost=_retained_bytes((units,lines))
                cached={'epoch':row['source_epoch'],'units':units,'lines':lines,'bytes':cost}
                if cost<=SOURCE_CACHE_BYTES:
                    while self._source_cache and (len(self._source_cache)>=4 or self._source_cache_bytes+cost>SOURCE_CACHE_BYTES):
                        _,removed=self._source_cache.popitem(last=False);self._source_cache_bytes-=removed['bytes']
                    self._source_cache[revision_id]=cached;self._source_cache_bytes+=cost
            if revision_id in self._source_cache: self._source_cache.move_to_end(revision_id)
            units=cached['units']
            entry=units[locator['unit']];unit=entry['text'];start,end=locator['char_start'],locator['char_end']
            if type(start) is not int or type(end) is not int or not 0<=start<end<=len(unit): raise ValueError('citation_range')
            expected={**entry['locator'],'unit':locator['unit'],'char_start':start,'char_end':end}
            if expected['kind']=='text':
                expected['line_start']=entry['locator']['line_start']+bisect_left(cached['lines'][locator['unit']],start)
                expected['line_end']=expected['line_start']+unit[start:end].rstrip('\n').count('\n')
            digest=hashlib.sha256(row['text'].encode()).hexdigest()
            encoded=json.dumps(locator,sort_keys=True,ensure_ascii=False)
            cid='cite_'+hashlib.sha256((project_id+':'+revision_id+':'+str(row['ordinal'])+':'+digest+':'+encoded).encode()).hexdigest()
            if unit[start:end]!=row['text'] or expected!=locator or digest!=row['text_hash'] or cid!=row['id']: raise ValueError('citation_source_mismatch')
        except (KeyError,IndexError,TypeError,ValueError): raise _error('Stored citation failed source verification',409)
        preview_start=max(0,start-300)
        return {'citation_id':row['id'],'document_id':row['document_id'],'filename':row['name'],'revision_id':row['revision_id'],
                'version':row['version'],'content_hash':row['content_hash'],'revision_time':row['revision_time'],'revision_basis':row['revision_basis'],
                'locator':locator,'quote':row['text'],'preview':unit[preview_start:min(len(unit),end+300)],'preview_start':preview_start,
                'superseded':row['current_revision']!=row['revision_id']}

    def knowledge_conflicts(self, project_id, query=None, candidate_ids=None):
        self.project(project_id)
        rows=[dict(r) for r in self.db.execute('''SELECT f.*,c.document_id,r.revision_time FROM document_facts f
        JOIN document_chunks c ON c.id=f.chunk_id JOIN documents d ON d.current_revision=c.revision_id
        JOIN document_revisions r ON r.id=c.revision_id WHERE f.project_id=? LIMIT 10001''',(project_id,))]
        groups={}
        for row in rows:
            key=row['scope'],row['subject'];groups.setdefault(key,[]).append(row)
        result=[];words=set(re.findall(r'\w+',query.casefold())) if query else set()
        for (scope,subject),facts in groups.items():
            values={re.sub(r'\s+',' ',x['value'].casefold()).strip(' .') for x in facts}
            if len(values)<2 or len({x['document_id'] for x in facts})<2: continue
            if query and not words.intersection(re.findall(r'\w+',subject)) and not {x['chunk_id'] for x in facts}.intersection(candidate_ids or []): continue
            facts=sorted(facts,key=lambda r:r['revision_time'],reverse=True)
            result.append({'subject':subject,'scope':scope,'preferred_citation_id':facts[0]['chunk_id'],
                           'evidence':[{'citation_id':f['chunk_id'],'document_id':f['document_id'],'value':f['value'],'revision_time':f['revision_time']} for f in facts[:10]],
                           'warning':'Potential source conflict; review the cited values. Most recent revision is preferred.'})
            if len(result)>=20: break
        return result
