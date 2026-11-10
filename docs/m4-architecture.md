# M4 manual assistance architecture

This extends the existing Electron/React/FastAPI/SQLite design. M2 retrieval and M3
capture/ASR workers remain in place. Selected-window vision and the full resource
scheduler belong to M5; screen context is explicitly unavailable in M4.

```mermaid
sequenceDiagram
    participant U as Button or native shortcut
    participant A as Local FastAPI
    participant S as SQLite
    participant D as Project retrieval
    participant O as Loopback Ollama
    U->>A: POST scoped request with UUID
    A->>S: Freeze confirmed transcript in previous 90 seconds
    A->>A: Extract latest explicit English/Bulgarian question
    alt No explicit question
        A->>S: Save no_question, no answer
    else Question found
        A-->>U: 202 accepted + request ID
        A->>D: Hybrid retrieval in the same project
        D-->>A: Verified source excerpts or explicit lexical warning
        A->>O: Bounded schema-constrained English briefing
        O-->>A: JSON + usage/duration measurements
        A->>A: Validate schema, language, categories and source allowlist
        A->>S: Revalidate sources, atomically save response
        A-->>U: WebSocket state revision; GET detail
    end
    Note over A,S: M3 transcript ingestion continues independently
```

## Trigger and context semantics

The Electron main process registers the existing configurable global shortcut. It
expands/focuses the companion and posts to the authenticated local API with a fresh
UUID. Buttons use the same endpoint. There is no answer-generation timer, transcript
watcher, browser/cloud service or automatic retry. Metadata diagnostics only read
local model tags. No-question requests do not call retrieval or the generator.

The service verifies project/session ownership, selected project, active/paused
session, UUID scope and the single-flight slot. Repeating the same UUID returns the
existing request without generating twice. A different request while busy receives
409; no generation queue is created. Request startup/cancellation shares the existing
session lifecycle lock, so pause/stop cannot race with a new request's admission.

Trigger time is wall clock minus session start, matching persisted M3 offsets. The
window is `[max(0, end-90), end]`, including only completely contained confirmed
segments. Segments crossing either boundary are omitted because word timestamps are
not stored. Pausing does not freeze wall-clock context age. A lag warning appears if
the latest included segment ends over five seconds before the trigger. Windows are
bounded to 500 segments/64,000 text characters; oversized requests fail explicitly.

The deterministic question gate uses English/Bulgarian interrogative patterns. It
rejects ordinary statements, several reported/quoted question forms and incomplete
auxiliary fragments. Adjacent segments merge only for the same speaker/source with
at most a 1.5-second gap. The latest candidate retains its exact segment IDs/times.
The snapshot is a private immutable in-memory list: later ASR/speaker updates never
change an admitted request. A SHA-256 of source IDs/text/times records its provenance.
This heuristic can miss ellipsis, indirect requests and unfamiliar phrasing; it is
not a language-understanding accuracy guarantee.

## Retrieval and generation

Only M2's project-scoped retrieval is used. Missing embeddings produce an explicit
keyword fallback warning. Conflict detection can promote a preferred newer source;
conflicts remain disclosed. Up to two relevant source excerpts are included. Source
strings and transcript text are JSON data under a fixed instruction, never executed
code or tools. Full project documents are never sent to generation.

The fixed first candidate is `qwen3-vl:8b-instruct-q4_K_M`, `num_ctx=4096`,
`num_predict=640`, temperature 0, `stream=false`, JSON-schema format, `keep_alive=5m`.
There is no automatic 4B/cloud fallback. Message JSON plus schema must fit 3,072 UTF-8
bytes; excerpts/context shrink before exceeding that bound. This conservatively
reserves room for 640 output tokens and template overhead. Returned token usage is
checked as well; real Qwen tokenizer/runtime compatibility still requires the laptop
test. Prompt truncation can reduce evidence/context usefulness and is disclosed.

The client connects only to `http://127.0.0.1:11434`, ignores inherited proxies, rejects
redirects and has a 55-second HTTP timeout. The entire retrieval/generation/validation
task has a 60-second deadline. Exact installed model name and a valid digest are
required; the digest must stay unchanged across generation. Complete assistant-only,
tool-free output and bounded nonnegative usage/duration metadata are required.

Generation and M2 embedding HTTP calls share a lock. Manual requests defer background
indexing even when the session is paused. M3 audio capture and isolated ASR/diarization
workers do not acquire that lock and are never stopped to run assistance. The current
safe starting configuration remains CPU Whisper Medium int8 and CPU diarization,
with generation using Ollama's GPU allocation. GPU Whisper is still selectable,
but concurrent VRAM suitability is unqualified. M4 does not enforce a VRAM reserve or
monitor other applications' Ollama work; the M5 scheduler remains necessary.

Set `OLLAMA_NUM_PARALLEL=1` for the Ollama server. Client cancellation closes the HTTP
request and rejects any late answer; server-side GPU cancellation timing is untested.
The server may finish already-admitted work before it observes the disconnect.

## Output trust and storage

Pydantic requires English-tagged JSON, one concise briefing, zero or 2–3 supporting
points, and up to three limitations. Offline deterministic langdetect plus Cyrillic
and first-person checks reject tested non-English/script forms. These are conservative
guards, not proof that every possible output is English or free of unsupported facts.

Each claim is labelled `project_document`, `general_technical_knowledge` or
`unverified_company_claim`. Document claims require exact IDs from the supplied source
allowlist. General/unknown claims cannot carry document citations. Unknown company
claims must state uncertainty; several specific-question/assertion patterns require
document evidence or an explicit unknown. Inline invented citation markers and URLs
are rejected. React renders plain escaped text, without Markdown/HTML execution.

Every used source is resolved again against the same project's immutable M2 revision,
quote, locator and hash before commit. Deleted, corrupted or newly superseded sources
fail the request. This establishes source identity and verifiability. **It does not
prove that a cited excerpt entails the generated claim.** Real-model factual grounding,
prompt-injection resilience and English/Bulgarian quality need human-scored tests.

SQLite stores `assistance_requests`, `detected_questions` and `generated_responses`.
Only validated bodies are saved, together with question/source IDs, window bounds/hash,
warnings, model digest and performance metrics. Prompts, full snapshot copies, raw
model output, audio and screenshots are not stored by M4. Response commit and terminal
request status are atomic. Requests left in flight across restart become interrupted.

History is scoped by project/session and lists the latest 30 requests. Detail reads
rehydrate citations from current stored sources. Deleted/corrupt sources have no
expandable citation; the saved claim stays visible with an explicit warning. Older
retained revisions show a superseded warning. Project/session deletion cascades, and
the existing transcript retention policy (default 30 days) also removes assistance
requests, derived questions and responses. This is logical deletion, not a forensic
erasure guarantee for filesystem backups or SQLite WAL copies.

Cancel, pause, stop, shutdown and parent death cancel pending work without saving a
partial answer. Early cancellation publishes idle state even if the background task
never started. Ordinary generation errors/timeouts release the slot and leave the
meeting active. The UI shows suppression, errors, progress, evidence labels, source
quotes and history in both views. A new request selects the latest result in both views.
