import hashlib
import json
from datetime import datetime,timezone
from uuid import uuid4

SCHEMA='''
CREATE TABLE IF NOT EXISTS assistance_requests(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 status TEXT NOT NULL, phase TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT,
 window_start REAL NOT NULL, window_end REAL NOT NULL, transcript_digest TEXT NOT NULL,
 question TEXT, segment_ids TEXT NOT NULL, error TEXT, warnings TEXT NOT NULL DEFAULT '[]', elapsed_ms INTEGER);
CREATE INDEX IF NOT EXISTS assistance_scope ON assistance_requests(project_id,session_id,created_at);
CREATE TABLE IF NOT EXISTS detected_questions(
 request_id TEXT PRIMARY KEY REFERENCES assistance_requests(id) ON DELETE CASCADE,
 question TEXT NOT NULL, source_segment_ids TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS generated_responses(
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE REFERENCES assistance_requests(id) ON DELETE CASCADE,
 body TEXT NOT NULL, model TEXT NOT NULL, model_digest TEXT NOT NULL, metrics TEXT NOT NULL, created_at TEXT NOT NULL);
'''


class AssistanceStore:
    def init_assistance(self):
        self.db.executescript(SCHEMA)
        with self.db:
            self.db.execute("UPDATE assistance_requests SET status='interrupted',phase='interrupted',completed_at=?,error='Application stopped before this request completed' WHERE status IN ('retrieving','generating','validating')",(datetime.now(timezone.utc).isoformat(),))

    def request_row(self, project_id, session_id, request_id):
        self.require_session(project_id,session_id)
        row=self.db.execute('SELECT * FROM assistance_requests WHERE id=? AND project_id=? AND session_id=?',(request_id,project_id,session_id)).fetchone()
        if not row:
            from .store import DomainError
            raise DomainError('Assistance request not found in this session',404)
        result=dict(row);result['segment_ids']=json.loads(result['segment_ids']);result['warnings']=json.loads(result['warnings'])
        return result

    def snapshot_window(self, project_id, session_id, now):
        session=self.require_session(project_id,session_id)
        end=max(0.,now-datetime.fromisoformat(session['started_at']).timestamp());start=max(0.,end-90)
        # Boundary-crossing segments are omitted because word timestamps aren't persisted.
        rows=[dict(r) for r in self.db.execute('''SELECT * FROM transcript_segments WHERE session_id=? AND start>=? AND end<=?
        ORDER BY start,end,id LIMIT 501''',(session_id,start,end))]
        digest=hashlib.sha256(json.dumps([(r['id'],r['text'],r['start'],r['end']) for r in rows],ensure_ascii=False).encode()).hexdigest()
        return start,end,rows,digest

    def record_assistance(self, request_id, project_id, session_id, start, end, digest, question, warnings):
        now=datetime.now(timezone.utc).isoformat();status='retrieving' if question else 'no_question'
        with self.db:
            self.db.execute('''INSERT INTO assistance_requests(id,project_id,session_id,status,phase,created_at,completed_at,window_start,window_end,transcript_digest,question,segment_ids,warnings)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(request_id,project_id,session_id,status,status,now,None if question else now,start,end,digest,question.text if question else None,json.dumps(question.segment_ids if question else []),json.dumps(warnings)))
            if question:self.db.execute('INSERT INTO detected_questions VALUES(?,?,?)',(request_id,question.text,json.dumps(question.segment_ids)))
            self.bump()

    def assistance_phase(self, request_id, phase):
        self.db.execute('UPDATE assistance_requests SET status=?,phase=? WHERE id=?',(phase,phase,request_id));self.bump()

    def finish_assistance(self, request_id, status, error, elapsed_ms, warnings=None):
        self.db.execute('UPDATE assistance_requests SET status=?,phase=?,completed_at=?,error=?,elapsed_ms=? WHERE id=?',
            (status,status,datetime.now(timezone.utc).isoformat(),error,elapsed_ms,request_id))
        if warnings is not None:self.db.execute('UPDATE assistance_requests SET warnings=? WHERE id=?',(json.dumps(warnings),request_id))
        self.bump()

    def save_response(self, request_id, body, model, digest, metrics):
        self.db.execute('INSERT INTO generated_responses VALUES(?,?,?,?,?,?,?)',
            (str(uuid4()),request_id,json.dumps(body,ensure_ascii=False),model,digest,json.dumps(metrics),datetime.now(timezone.utc).isoformat()))

    def assistance_detail(self, project_id, session_id, request_id):
        row=self.request_row(project_id,session_id,request_id)
        response=self.db.execute('SELECT * FROM generated_responses WHERE request_id=?',(request_id,)).fetchone()
        if not response:return {**row,'response':None,'citations':[],'unavailable_citations':[]}
        body=json.loads(response['body']);ids=list(dict.fromkeys(cid for claim in [body['briefing'],*body['supporting_points']] for cid in claim['citation_ids']))
        citations=[];invalid=[]
        from .store import DomainError
        for cid in ids:
            try:citations.append(self.citation(project_id,cid))
            except DomainError:invalid.append(cid)
        return {**row,'response':{'id':response['id'],'body':body,'model':response['model'],'model_digest':response['model_digest'],'metrics':json.loads(response['metrics'])},
                'citations':citations,'unavailable_citations':invalid}

    def assistance_history(self, project_id, session_id):
        self.require_session(project_id,session_id)
        ids=self.db.execute('SELECT id FROM assistance_requests WHERE project_id=? AND session_id=? ORDER BY created_at DESC LIMIT 30',(project_id,session_id)).fetchall()
        return [self.assistance_detail(project_id,session_id,r['id']) for r in ids]
