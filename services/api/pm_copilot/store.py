import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class DomainError(Exception):
    def __init__(self, message, status=409):
        self.message, self.status = message, status


from .transcript_store import TranscriptStore, SCHEMA
from .document_store import DocumentStore
from .assistance_store import AssistanceStore


class Store(TranscriptStore, DocumentStore, AssistanceStore):
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          state TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, consent INTEGER NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_live_session ON sessions((1)) WHERE state IN ('active','paused');
        INSERT OR IGNORE INTO settings VALUES('revision','0');
        INSERT OR IGNORE INTO settings VALUES('shortcut','Control+Shift+Space');
        ''')
        self.db.executescript(SCHEMA)
        self.init_documents()
        self.init_assistance()
        if 'manual' not in {row[1] for row in self.db.execute('PRAGMA table_info(speakers)')}:
            self.db.execute('ALTER TABLE speakers ADD COLUMN manual INTEGER NOT NULL DEFAULT 0')
            self.db.commit()
        self.purge_transcripts()
        with self.db:
            recovered = self.db.execute("UPDATE sessions SET state='interrupted', ended_at=? WHERE state IN ('active','paused')", (now(),)).rowcount
            if recovered:
                self.bump()

    def close(self):
        self.db.close()

    def value(self, key, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def setting(self, key, value):
        self.db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))

    def bump(self):
        self.setting('revision', str(int(self.value('revision'))+1))

    def project(self, project_id):
        row = self.db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise DomainError('Project not found', 404)
        return dict(row)

    def live(self):
        return self.db.execute("SELECT * FROM sessions WHERE state IN ('active','paused')").fetchone()

    def snapshot(self):
        sessions = [dict(x) for x in self.db.execute('SELECT * FROM sessions ORDER BY started_at DESC LIMIT 20')]
        return {'revision': int(self.value('revision')), 'projects': [dict(x) for x in self.db.execute('SELECT * FROM projects ORDER BY created_at,id')],
                'selected_project_id': self.value('selected_project_id') or None,
                'session': sessions[0] if sessions else None, 'sessions': sessions,
                'shortcut': self.value('shortcut'), 'capabilities': {'audio_capture': False, 'assistance': False}}

    def create(self, name):
        with self.db:
            self.db.execute('INSERT INTO projects VALUES(?,?,?)', (str(uuid4()), name, now()))
            self.bump()
        return self.snapshot()

    def rename(self, project_id, name):
        self.project(project_id)
        with self.db:
            self.db.execute('UPDATE projects SET name=? WHERE id=?', (name, project_id))
            self.bump()
        return self.snapshot()

    def select(self, project_id):
        self.project(project_id)
        live = self.live()
        if live and live['project_id'] != project_id:
            raise DomainError('Stop the current session before switching projects')
        with self.db:
            self.setting('selected_project_id', project_id)
            self.bump()
        return self.snapshot()

    def delete(self, project_id):
        self.project(project_id)
        if self.live() and self.live()['project_id'] == project_id:
            raise DomainError('Stop the current session before deleting its project')
        with self.db:
            self.drop_project_knowledge(project_id)
            self.db.execute('DELETE FROM projects WHERE id=?', (project_id,))
            if self.value('selected_project_id') == project_id:
                self.setting('selected_project_id', '')
            self.bump()
        return self.snapshot()

    def start(self, project_id, consent):
        if not consent:
            raise DomainError('Recording consent acknowledgement required', 422)
        self.project(project_id)
        if project_id != self.value('selected_project_id'):
            raise DomainError('Project selection changed; review the project before starting')
        if self.live():
            raise DomainError('A session is already active')
        with self.db:
            self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)', (str(uuid4()), project_id, 'active', now(), None, 1))
            self.bump()
        return self.snapshot()

    def transition(self, session_id, action):
        row = self.live()
        if not row or row['id'] != session_id:
            raise DomainError('Session is no longer active')
        target = {('active','pause'):'paused', ('paused','resume'):'active', ('active','stop'):'stopped', ('paused','stop'):'stopped'}.get((row['state'], action))
        if not target:
            raise DomainError('Invalid session transition')
        with self.db:
            self.db.execute('UPDATE sessions SET state=?, ended_at=? WHERE id=?', (target, now() if target=='stopped' else None, session_id))
            self.bump()
        return self.snapshot()

    def shortcut(self, accelerator):
        with self.db:
            self.setting('shortcut', accelerator)
            self.bump()
        return self.snapshot()
