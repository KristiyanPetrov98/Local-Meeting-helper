# Milestone 4 implementation and validation

Date: 2026-11-08. M4 code is implemented and portable checks pass. Live Ollama answer
quality, Windows operation and RTX 4080 concurrent inference are **not qualified**.
Work stops at M4. M5–M7 have not been implemented.

## Features implemented

- Real Electron global-shortcut and dashboard/companion button requests.
- Frozen previous-90-second confirmed transcript context and conservative explicit
  English/Bulgarian question detection. No question means no retrieval or generation.
- Project-isolated M2 retrieval, explicit keyword fallback, bounded 8B Ollama generation.
- English factual briefing format, optional 2–3 supporting points, evidence categories,
  source allowlist/revalidation, and refusal to save invalid/incomplete output.
- Asynchronous single-flight requests, UUID idempotency, live progress, cancellation,
  timeout/session-shutdown recovery and independent transcript ingestion.
- Persisted scoped response history, expandable verifiable citations, unavailable-source
  warnings, model digest/usage/timing metadata and retention of derived text.
- Dependency lock, Windows setup script, automated tests and architecture documentation.

## Files and components

New API modules: `questions.py`, `briefing.py`, `generation.py`, `assistance.py`,
`assistance_store.py`, `assistance_api.py` under `services/api/pm_copilot/`.
Integration changes: `app.py`, `store.py`, `transcript_store.py`, `documents.py`,
`__main__.py`. The existing M2 parser/citation path and M3 workers are retained.

Desktop/UI: `apps/desktop/src/main.ts`, new `apps/web/src/AssistancePanel.tsx`,
`apps/web/src/main.tsx`, `styles.css`, generated OpenAPI/TypeScript contracts and native
status types. Tests: new `tests/api/test_assistance.py`, `tests/e2e/m4.spec.ts`, updated
M1 capability/error-locator expectations. Setup: `scripts/setup-m4.ps1`,
`requirements-assistance.in/.lock`, application CI dependency install, README/component
guides and [M4 architecture](m4-architecture.md).

## Tests executed

Final Linux results: **157 passed, zero failed, zero skipped**.

| Check | Result |
| --- | --- |
| Full API/parser/capture-pipeline suite | 137 passed, including 67 M4 cases |
| Real Electron/Playwright workflows | 8 passed, including 2 M4 cases |
| Vitest shell checks | 4 passed |
| M0 feasibility regression checks | 5 passed |
| .NET audio conversion/protocol tests | 3 passed |
| Generated contracts/schema consistency | Passed |
| TypeScript type checks and production web/desktop build | Passed |
| Python compilation and pip dependency consistency | Passed |

API tests use explicit test-only generator/embedding fixtures, real SQLite/FTS and
the real parser, allowlist and validation pipeline. They test bilingual question
gating, statements/quoted forms, stale/future/boundary context, frozen in-flight
context, project isolation, no-question zero calls, idempotency, single-flight rejection,
concurrent transcript storage, paused-session indexing deferral, timeout, cancel,
early-cancel state publication, session stop/pause, database restart, retention,
source deletion/revision/model changes, language/category/schema checks and the
actual Ollama HTTP payload/response-validation code through MockTransport.

Electron tests launched the actual application and Python service. They exercised
native X11 shortcut delivery, buttons, shared state, genuine missing-model errors,
document upload/parser/FTS/citation resolution, saved-response display, deleted-source
warnings, project switching and restart. Successful response display uses a labelled
SQLite fixture; no successful real-model generation is claimed. No production fake
model/transcript mode was added.

An initial run exposed a WebSocket disconnect cancellation race; the handler now
drains a closing connection without surfacing cancellation as an application error.
The regression suite passes after the fix. Desktop test corrections scoped an alert
to its original banner and used the existing octet-stream upload contract. A request
admission/cancellation race was also fixed with the shared session lifecycle lock.

Machine-readable results: [m4-validation.json](m4-validation.json).
Installed dependency evidence: [m4-dependencies.json](m4-dependencies.json).

## Acceptance criteria

| Criterion | Status and evidence |
| --- | --- |
| Application starts; shortcut/button reach real local API | Passed on Linux Electron/X11 |
| Previous 90 seconds, latest explicit question, no-question suppression | Passed for automated fixtures; linguistic coverage limited |
| Same-project evidence and valid source references | Passed parser/API/UI cases |
| Invalid, first-person and tested non-English responses not saved | Passed fixture cases |
| Single request, cancellation, persistence and session isolation | Passed API and desktop cases |
| Transcript ingestion continues while generation is pending | Passed with concurrent text/storage fixtures |
| Actual Qwen3-VL 8B briefing quality and token/runtime compatibility | Unrun; local runtime/weights unavailable |
| Real Bulgarian/English Whisper while 8B responds | Unrun; Windows audio/GPU/models unavailable |
| Windows hotkey, Meet devices and RTX 4080 stability/latency/VRAM | Unrun; must be tested on the laptop |
| Recent selected-window context | Explicitly unavailable; M5 scope |

No acceptance criterion is passed from file creation alone. Portable implementation
validation is complete; the unrun target-machine criteria remain open.

## Measured results and limitations

The cloud has Python 3.12.14, no Ollama CLI, no reachable service on 127.0.0.1:11434,
and no nvidia-smi. A registry request through the configured proxy returned CONNECT
403 on this date. The real-model attempt cannot proceed here. GPU memory, primary-model
latency, answer accuracy and concurrent ASR stability therefore have **no measurements**;
they are not recorded as zero or passed. Fixture timings are not hardware benchmarks.

The question detector intentionally favors clear direct questions. It can miss implicit,
elliptical or unfamiliar wording, and ASR errors can change detection. Snapshot boundaries
drop crossing segments. Budgeted context/excerpts can omit useful facts. Structural
and source validation establish source identity, not semantic entailment. Language
identification and company-claim heuristics are imperfect; review every briefing's
evidence before using it. The 60-second deadline may reject a cold model start.

The recommended **provisional starting configuration** is Qwen3-VL 8B Q4_K_M at
4,096 tokens, output cap 640, Ollama parallelism 1, CPU Whisper Medium int8, CPU
Community-1 and CPU query embeddings. The primary 8B model stays selected. No automatic
4B fallback or context increase was introduced. This profile needs laptop measurements;
GPU Whisper and 6,144/8,192 contexts are not qualified. M4 shares the embedding/generation
lock and defers indexing, but has no VRAM monitoring/reserve enforcement. Ollama server
cancellation timing and coexistence with external Ollama clients are untested.

M5 supplies vision/sharing safeguards and full GPU scheduling; M6 supplies onboarding
and installer work. Do not treat current content protection as verified Meet sharing
exclusion. Windows setup scripts and Windows CI are supplied but were not run here.

## Manual test on the Windows 11 RTX 4080 laptop

1. Install Node 24, Python 3.12 x64, .NET SDK 8.0.427 and local Ollama. From the repo
   run `scripts/setup-m3.ps1`, install the local Whisper Medium/Community-1 assets as
   described in [M3](milestone-3.md), then run `scripts/setup-m4.ps1`.
   M4's lock includes M2 dependencies and adds langdetect 1.0.9 plus six 1.17.0.
   Installation requires Internet/package access once; inference uses local assets.
2. Quit an existing Ollama tray server if needed. In a PowerShell terminal set
   `$env:OLLAMA_NUM_PARALLEL='1'`, then start `ollama serve`. In another terminal run
   `ollama pull qwen3-vl:8b-instruct-q4_K_M` and `ollama pull qwen3-embedding:0.6b`.
   Record the actual model digests. Do not substitute 4B before measuring 8B.
3. Run `npm start`. Create/select Alpha and import a text file containing
   `The release is scheduled for Friday.` Wait for indexing. Check model status;
   if weights/runtime are missing, the UI must say so rather than invent an answer.
4. Configure the same mic/output as Meet in **Audio & transcript**, start with CPU
   ASR, and use a consented test meeting. Enable capture explicitly when starting.
   Confirm real English/Bulgarian sentences and provisional speakers appear first.
5. Say statements only, wait for confirmation, then press Ctrl+Shift+Space. Expect
   **No explicit question found… No answer was generated.** Confirm request history
   has `no_question`, no response, and no Ollama generation. Capture must continue.
6. Ask `When is the release?`, wait for its transcript, then use the shortcut or
   **Request briefing**. Expect local progress and an English factual briefing. Expand
   the evidence and check filename/revision, exact source location/quote and meaning.
   Repeat in Bulgarian: `Кога е пускането?`. Score the actual model's response manually.
7. Ask a general technical question, then a company-specific question without evidence.
   Check general-knowledge versus explicit unknown labels. Import conflicting dated
   facts and verify the response uses/reviews newer evidence and discloses conflict.
8. While generation is pending, keep speaking. Verify transcript timestamps keep
   advancing and packet/chunk counts, queue depth, gaps and ASR errors remain healthy.
   Press the shortcut repeatedly: no additional request queue should appear. Test
   Cancel, pause and stop; no partial answer should be saved. Resume capture normally.
9. Stop, review history, restart, and verify saved answers/citations. Delete an evidence
   document: the saved answer must warn that its source is unavailable. Create Beta:
   Alpha documents, transcripts and answers must not appear. Re-select Alpha to review.
10. Once all assets are installed, disconnect external networking and repeat. Test
    both the Electron dashboard and **Desktop settings → Open in browser**. Loopback
    must remain available. Never share the temporary browser authentication link.

For target-machine qualification, run at least a 30-minute consented bilingual test,
including cold/warm requests and continuous speech during generation. Record hardware
inventory using the M0 probe and monitor actual GPU memory, for example:

```powershell
nvidia-smi --query-gpu=timestamp,memory.used,memory.free,utilization.gpu --format=csv -l 1 > m4-gpu.csv
```

Record request elapsed_ms, model digest, prompt/output counts and Ollama load/evaluation
durations from saved request details (durations are nanoseconds), peak VRAM, free VRAM,
transcription lag/gaps/drops, and independently scored grounding/language. Keep at least
the spec's approximately 2 GB VRAM reserve as the initial target. Test GPU Whisper only
after establishing the CPU baseline. The existing M0 benchmark procedure describes
separate isolated/concurrent runs. Do not claim this qualification passed until these
tests have actually run on the laptop.

## Reproduce portable checks

Use an activated Python 3.12 environment with the development and assistance locks:

```powershell
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-dev.lock -r services/api/requirements-assistance.lock
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m pytest tests/api -q
.\.venv\Scripts\python -m unittest discover -s tests -v
npm run contracts
npm run typecheck
npm test
npm run build
dotnet test tests/capture-dotnet
npx playwright install chromium
npm run test:e2e
```

The cloud run used Xorg's dummy display, system Chromium, `PM_TEST_X11_INPUT=1` and
the existing .NET SDK. Portable Windows execution may skip POSIX-only subprocess
fixtures. PowerShell commands above are reproduction instructions, not Windows passes.
