# Local service (M1 through M6)

Authenticated loopback FastAPI/SQLite, shared snapshots, scoped text transcripts,
speaker edits, retention and isolated audio/model workers. Electron supplies private
bootstrap over stdin and keeps the pipe open for parent-death detection.

Base requirements.lock supports shell-only sessions; requirements-asr.lock adds local
Whisper. Optional requirements-diarization-windows.lock adds CPU Community-1 dependencies
for the target Windows environment. Model assets are installed separately, never
retrieved during a meeting. requirements-documents.lock adds the M2 parser/search dependencies. Project-scoped
document, search and citation routes now exist. requirements-assistance.lock includes
these dependencies plus offline language validation for M4 manual briefings.

M4 adds authenticated, project/session-scoped assistance requests, a frozen 90-second
confirmed transcript snapshot, explicit-question suppression, bounded local Ollama
generation and validated response/citation history. Requests are asynchronous and
cancellable, with one heavy generation at a time. No generation pauses the M3 worker.
See docs/m4-architecture.md and docs/milestone-4.md for validation boundaries and
unrun laptop/model checks. Model weights and live Windows tests remain separate.

Run pytest tests/api from the repository root. Portable test fixtures explicitly
exclude real hardware capture; actual audio testing requires consent and Windows.

M5 adds a separate WGC process, bounded RAM frames, visual/risk output validation,
resource leases and sharing state. Manual admission preempts optional inference; ASR
never takes that lock. Only resource settings persist. See docs/m5-architecture.md.

M6 adds fixed source/frozen worker dispatch, managed model installation/recovery,
setup runs and actual offline/live measurement flows. No imported asset is marked
inference-verified from file creation. See docs/m6-architecture.md.
