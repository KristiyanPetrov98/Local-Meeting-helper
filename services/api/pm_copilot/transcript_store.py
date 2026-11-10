import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from .audio import overlap

SCHEMA = '''
PRAGMA secure_delete=ON;
CREATE TABLE IF NOT EXISTS speakers(
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 name TEXT NOT NULL, merged_into TEXT REFERENCES speakers(id), manual INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS transcript_segments(
 id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 source TEXT NOT NULL CHECK(source IN ('local','remote')), start REAL NOT NULL, end REAL NOT NULL,
 text TEXT NOT NULL, language TEXT NOT NULL, speaker_id TEXT NOT NULL REFERENCES speakers(id),
 segment_key TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(session_id,source,segment_key));
CREATE INDEX IF NOT EXISTS transcript_session ON transcript_segments(session_id,id);
'''


class TranscriptStore:
    def require_session(self, project_id, session_id):
        self.project(project_id)
        row = self.db.execute('SELECT * FROM sessions WHERE id=? AND project_id=?',(session_id,project_id)).fetchone()
        if not row:
            from .store import DomainError
            raise DomainError('Session not found in this project',404)
        return dict(row)

    def speaker(self, session_id, label):
        speaker_id = session_id+':'+label
        name = 'You' if label=='local' else 'Remote (unrefined)' if label=='remote' else 'Speaker '+label.removeprefix('speaker-')
        self.db.execute('INSERT OR IGNORE INTO speakers(id,session_id,name,merged_into) VALUES(?,?,?,NULL)',(speaker_id,session_id,name))
        return self.canonical(session_id,speaker_id)

    def canonical(self, session_id, speaker_id):
        for _ in range(100):
            row = self.db.execute('SELECT * FROM speakers WHERE id=? AND session_id=?',(speaker_id,session_id)).fetchone()
            if not row:
                from .store import DomainError
                raise DomainError('Speaker not found in this session',404)
            if not row['merged_into']: return speaker_id
            speaker_id = row['merged_into']
        raise ValueError('speaker_alias_cycle')

    def add_segment(self, session_id, source, start, end, text, language, key, echo=False):
        from .store import now
        if source not in ('local','remote') or not text.strip() or not 0 <= start < end or len(text)>8000:
            raise ValueError('invalid_transcript_segment')
        session = self.db.execute('SELECT id FROM sessions WHERE id=?',(session_id,)).fetchone()
        if not session: return self.snapshot()
        norm = lambda s: re.sub(r'\W+',' ',s.casefold()).strip()
        with self.db:
            if echo:
                other = 'remote' if source=='local' else 'local'
                nearby = self.db.execute('SELECT * FROM transcript_segments WHERE session_id=? AND source=? AND start<? AND end>?',(session_id,other,end+1,start-1)).fetchall()
                for row in nearby:
                    # Conservative transcript-level echo dedupe, NOT acoustic cancellation.
                    if overlap(start,end,row['start']-1,row['end']+1)>0 and len(norm(text))>=12 and SequenceMatcher(None,norm(text),norm(row['text'])).ratio()>.94:
                        if source=='local': return self.snapshot()
                        self.db.execute('DELETE FROM transcript_segments WHERE id=?',(row['id'],))
            sid = self.speaker(session_id,source)
            self.db.execute('INSERT OR IGNORE INTO transcript_segments(session_id,source,start,end,text,language,speaker_id,segment_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (session_id,source,start,end,text.strip(),language,sid,key,now()))
            self.bump()
        return self.snapshot()

    def refine_speakers(self, session_id, turns):
        if not turns: return self.snapshot()
        lo,hi = min(t['start'] for t in turns),max(t['end'] for t in turns)
        rows = self.db.execute("SELECT * FROM transcript_segments WHERE session_id=? AND source='remote' AND start<? AND end>?",(session_id,hi,lo)).fetchall()
        with self.db:
            for row in rows:
                if self.db.execute('SELECT manual FROM speakers WHERE id=?',(row['speaker_id'],)).fetchone()[0]: continue
                turn = max(turns,key=lambda t:overlap(row['start'],row['end'],t['start'],t['end']))
                if overlap(row['start'],row['end'],turn['start'],turn['end'])>0:
                    sid = self.speaker(session_id,turn['speaker'])
                    self.db.execute('UPDATE transcript_segments SET speaker_id=? WHERE id=?',(sid,row['id']))
            self.bump()
        return self.snapshot()

    def transcript(self, project_id, session_id, before=None, limit=200):
        self.require_session(project_id,session_id)
        before = before if before is not None else 2**63-1
        rows = [dict(x) for x in self.db.execute('SELECT * FROM transcript_segments WHERE session_id=? AND id<? ORDER BY id DESC LIMIT ?', (session_id,before,limit))]
        rows.reverse()
        return {'segments':rows,'speakers':[dict(x) for x in self.db.execute('SELECT id,name FROM speakers WHERE session_id=? AND merged_into IS NULL',(session_id,))],
                'older_cursor':rows[0]['id'] if len(rows)==limit else None}

    def rename_speaker(self, project_id, session_id, speaker_id, name):
        self.require_session(project_id,session_id)
        speaker_id = self.canonical(session_id,speaker_id)
        with self.db:
            self.db.execute('UPDATE speakers SET name=?, manual=1 WHERE id=?',(name,speaker_id));self.bump()
        return self.snapshot()

    def merge_speakers(self, project_id, session_id, speaker_id, target):
        self.require_session(project_id,session_id)
        source = self.canonical(session_id,speaker_id);target = self.canonical(session_id,target)
        if source==target:
            from .store import DomainError
            raise DomainError('Select two different speakers',422)
        with self.db:
            self.db.execute('UPDATE transcript_segments SET speaker_id=? WHERE session_id=? AND speaker_id=?',(target,session_id,source))
            self.db.execute('UPDATE speakers SET merged_into=? WHERE id=?',(target,source))
            self.db.execute('UPDATE speakers SET manual=1 WHERE id=?',(target,));self.bump()
        return self.snapshot()

    def purge_transcripts(self):
        cutoff = (datetime.now(timezone.utc)-timedelta(days=int(self.value('retention_days','30')))).isoformat()
        with self.db:
            n = self.db.execute('DELETE FROM transcript_segments WHERE created_at<?',(cutoff,)).rowcount
            n += self.db.execute('DELETE FROM assistance_requests WHERE created_at<?',(cutoff,)).rowcount
            if n: self.bump()
        return self.snapshot()
