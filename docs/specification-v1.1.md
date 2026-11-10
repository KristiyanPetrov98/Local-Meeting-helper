# PM Copilot — Implementation Specification v1.1
## Windows 11 · RTX 4080 Laptop · Fully Local AI

### 1. Objective

Build a locally running, Cluely-style AI meeting assistant for Product Managers working in software and IT companies.

The application listens to Google Meet conversations, maintains a continuously updated transcript, searches project-specific documents, and analyzes a selected application window.

When the user presses a global keyboard shortcut, it analyzes the previous 90 seconds, identifies the latest explicit question, and generates a concise, evidence-backed factual briefing that the PM can paraphrase.

The system must not automatically generate meeting answers.

All AI inference, speech recognition, screen interpretation, document processing, and retrieval must operate locally.

**Primary implementation target: RTX 4080 Laptop GPU.**

Accuracy and stability take precedence over absolute speed.

### 2. Primary hardware

Develop, optimize, and test first on:

- Windows 11 x64.
- NVIDIA RTX 4080 Laptop GPU, standard 12 GB VRAM configuration.
- 64 GB system RAM.
- Approximately 20 CPU cores.
- Two monitors.
- Google Chrome and Google Meet.
- Headphones and external speakers.

Confirm actual GPU memory, power limits, driver version, available VRAM, and runtime capabilities rather than relying on assumed specifications.

Secondary validation target: RTX 3090 Ti desktop with 24 GB VRAM.

Do not optimize the product around 24 GB VRAM or require that capacity for the MVP.

### 3. Technology stack

Use:

- Electron + TypeScript for the Windows shell, native mini window, global shortcut, tray, and process management.
- React + Vite + TypeScript for the local browser dashboard.
- Tailwind CSS and shadcn/ui for the frontend.
- Python FastAPI for orchestration, document processing, AI inference coordination, and local APIs.
- C#/.NET Windows helper for audio loopback and selected-window capture.
- SQLite + FTS5 for persistent application data and lexical retrieval.
- Local embeddings + NumPy vector similarity for semantic retrieval.
- Ollama for local LLM, multimodal inference, and embedding models.
- faster-whisper for Bulgarian and English ASR.
- pyannote Community-1 for offline speaker diarization.
- WebSocket for live application events.
- pytest, Vitest, Playwright, and Windows integration tests.

The browser dashboard and mini window must share the same local application state.

There must be no cloud backend, user account requirement, hosted inference, or telemetry dependency.

### 4. Laptop-first AI configuration

#### Primary generation model

Use `qwen3-vl:8b-instruct-q4_K_M` as the first candidate for both answer generation and screen understanding.

Test it on the RTX 4080 Laptop GPU before changing models.

Start with a 4,096-token context budget and measure memory usage. Evaluate 6,144 and 8,192 tokens only when sufficient GPU memory remains.

Context requirements must be satisfied through retrieval and summarization, not by feeding entire project documents to the model.

#### Fallback generation model

Use `qwen3-vl:4b-instruct-q4_K_M` only when:

- The 8B model cannot run reliably within available VRAM.
- Measured answer latency becomes unacceptable.
- The user explicitly selects the lower-resource profile.

Do not automatically prefer the smaller model simply because it is faster.

#### Speech recognition

Start with multilingual Whisper Medium through faster-whisper.

Benchmark:

1. GPU `int8_float16` or other supported efficient GPU mode.
2. CPU `int8`.
3. Smaller multilingual Whisper configurations if the primary model cannot meet continuous transcription requirements.

Choose the most accurate configuration that can continuously transcribe a real meeting while the 8B model is responding.

The audio pipeline must never stop capturing speech merely because an LLM request is running.

#### Speaker diarization

Use pyannote Community-1, initially on CPU.

Assign remote speakers stable provisional labels such as Speaker 1, Speaker 2, and Speaker 3.

Allow manual renaming and merging.

Do not automatically invent participant names.

Schedule diarization refinement at lower priority than transcription and manual question answering.

#### Embeddings

Use `qwen3-embedding:0.6b`.

Run document indexing outside active meeting sessions where practical.

Persist embeddings so documents are not repeatedly reprocessed.

Run query embeddings on CPU when possible, or temporarily use the GPU through the model scheduler.

Do not retain the embedding model in GPU memory when doing so threatens the generation model's available memory.

### 5. GPU resource management

Implement a resource-aware inference scheduler.

Requirements:

- Detect total and currently available GPU memory.
- Monitor model residency, allocations, failures, and inference times.
- Leave a configurable VRAM reserve, initially targeting approximately 2 GB.
- Prioritize continuous audio capture and transcription over all optional AI work.
- Allow only one active heavy Ollama generation request by default.
- Set `OLLAMA_NUM_PARALLEL=1` initially.
- Manage model unloading through Ollama's `keep_alive` controls.
- Use bounded context sizes.
- Prevent uncontrolled inference queues.
- Cancel, defer, or suspend low-priority jobs when resources are constrained.
- Never silently fall back to cloud inference.

Execution priorities:

1. Audio capture and buffer integrity.
2. Continuous transcription.
3. User-triggered answer generation.
4. Project document retrieval.
5. Screen-change analysis.
6. Background risk identification.
7. Speaker refinement.
8. Document indexing.

During a user-triggered answer:

- Pause competing vision and risk-analysis jobs.
- Preserve uninterrupted audio capture.
- Continue transcription using the validated ASR execution path.
- Retrieve only the most relevant source chunks.
- Generate the answer using the primary 8B model when available.
- Resume deferred work after the answer completes.

The scheduler must support a CPU/GPU hybrid execution strategy.

It must not assume that all AI models can remain resident simultaneously.

When available VRAM is insufficient, gracefully reduce concurrent model usage, move supported workloads to CPU, reduce context size, or select the validated 4B fallback.

Display meaningful degraded-mode warnings to the user.

### 6. Product UX and core features

#### Main dashboard

Implement a local browser dashboard supporting:

- Project creation, renaming, deletion, and selection.
- Manual drag-and-drop document upload.
- Document indexing progress and error handling.
- Project-specific knowledge search.
- Local meeting history.
- Transcript and answer review.
- Speaker renaming/merging.
- Model and hardware configuration.
- Privacy and retention settings.
- Audio-device and screen-source selection.
- Setup and dependency diagnostics.

#### Mini window

Build an always-on-top Electron window supporting:

- Current project.
- Listening/paused state.
- Active meeting duration.
- Discreet risk indicator.
- Shortcut-triggered response generation.
- Concise answer with 2–3 supporting points.
- Expandable document citations.
- Collapse, expand, dismiss, and stop actions.

The interface must work effectively with two monitors.

Default shortcut: `Ctrl+Shift+Space`, configurable.

Support shortcut conflict detection.

#### Core assistance behavior

On shortcut:

1. Snapshot the previous 90 seconds of transcript.
2. Detect the most recent explicit question.
3. Stop without generating an answer if there is no question.
4. Resolve the question using relevant conversation context.
5. Retrieve project-specific documentation.
6. Include relevant recent screen context if available.
7. Generate a factual English briefing.
8. Add 2–3 supporting points when warranted.
9. Validate all citations.
10. Save the answer locally and display it.

Do not produce artificial first-person scripts.

Use English for answers even when the meeting is in Bulgarian.

Clearly distinguish project-document evidence, general technical knowledge, and unverified company-specific claims.

### 7. Meeting audio

Capture:

- User microphone.
- Google Meet playback audio through Windows process loopback when feasible.
- Selected system output loopback as fallback.

Support both headphones and external speakers.

Prevent duplicate transcript segments caused by microphone echo or simultaneous audio sources.

Handle device changes, disconnections, and temporary capture failures.

User must manually start and stop each meeting session after confirming recording consent.

Never persist raw audio, intermediate audio files, or meeting recordings.

### 8. Screen understanding

User selects an application window before starting a meeting.

Use Windows.Graphics.Capture.

Perform lightweight screen-change detection, then invoke the same Qwen3-VL model used for answers only when meaningful changes occur and resource budgets permit.

Initially:

- Debounce visual changes.
- Require approximately 1.5 seconds of stability.
- Rate-limit background vision inference to approximately one request every 10 seconds.
- Give user-triggered answer generation priority.

Do not save screenshots or video.

Preserve temporary visual observations only as long as necessary to answer relevant questions.

If screen capture fails or the GPU is busy, continue audio/document assistance.

### 9. Google Meet sharing safety

Until capture exclusion is verified:

- Support tab-only sharing as the approved workflow.
- Require acknowledgement of the supported sharing mode.
- Document how to share an individual Chrome tab.
- Use Electron's Windows content-protection capability as defense in depth.
- Do not claim guaranteed invisibility across capture modes.
- Hide the mini window during unverified broader sharing modes.
- Provide a preview-based verification workflow.

Recognize that the application cannot directly enforce Google Meet's native share-picker selection.

Use visible capture status and explicit user controls. Do not implement covert recording.

### 10. Project document intelligence

Each project has its own completely isolated knowledge base.

Support:

- PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown.
- Common code files, including Python, TypeScript, JavaScript, C#, Java, Go, Rust, and SQL.
- JSON, YAML, XML, GraphQL, Proto, and OpenAPI specifications.

Implement:

- Import validation.
- Content hashing.
- Original revision metadata extraction.
- Structure-aware chunking.
- Local embeddings.
- Hybrid lexical/semantic search.
- Relevance ranking.
- Exact citation metadata.
- Incremental reindexing.
- Source previews.
- Project-safe deletion.

Document scale: under 50 documents per project initially.

For conflicting sources, prefer the newest relevant document based on its original internal revision timestamp when available; otherwise use filesystem modification time, then import time.

Flag material contradictions.

Citations must resolve to source file IDs and original page, heading, slide, spreadsheet range, endpoint, or code line numbers.

Do not allow model-invented citations.

OCR for scanned documents belongs to Phase 2.

### 11. Background risk intelligence

Provide low-priority detection of:

- Technical feasibility concerns.
- Contradictions with documentation.
- Unresolved requirements.
- Missing dependencies.
- Security, scalability, and performance implications.

Background analysis must never generate unsolicited meeting answers.

Show an unobtrusive indicator that the user can click to inspect.

Suspend or defer risk analysis when the laptop's resources are required for transcription or manual assistance.

Do not persist unseen risk findings by default.

### 12. Data and local APIs

Use SQLite for:

- Projects.
- Documents.
- Document chunks.
- Embeddings.
- Sessions.
- Speakers.
- Transcript segments.
- Detected questions.
- Generated responses.
- Citations.
- Risk findings.
- Application settings.

Persist documents, transcripts, and AI suggestions locally.

Do not persist raw audio or screen images.

Default transcript retention: 30 days, configurable.

Expose authenticated loopback-only REST endpoints and typed WebSocket events for:

- Setup and hardware status.
- Project/document management.
- Search.
- Meeting start/stop.
- Transcript updates.
- Speaker corrections.
- Manual assistance.
- Answer history.
- Settings.
- Errors and resource-state updates.

Generate an OpenAPI schema and validate frontend/backend contracts.

Protect the localhost API from unauthorized browser origins, cross-project access, and arbitrary file operations.

### 13. Packaging and onboarding

Produce a Windows x64 installer.

Users must not need developer tools to run the packaged app.

Create a guided setup wizard that:

- Detects laptop hardware and GPU resources.
- Checks Ollama and supporting runtime dependencies.
- Guides first-time dependency/model installation.
- Confirms model licenses and access requirements.
- Downloads approved model files once.
- Benchmarks ASR and generation on the actual device.
- Chooses a validated performance profile.
- Tests microphone and Meet audio.
- Tests selected-window capture.
- Verifies local-only inference.
- Explains the Google Meet sharing limitation.

Do not package unlicensed model weights.

Ensure all packaged helper processes can start and shut down safely.

### 14. Security requirements

- All application APIs bound to loopback only.
- Authenticated access between Electron, the browser dashboard, and FastAPI.
- Strict origin and host validation.
- Electron context isolation and sandboxed renderer.
- Restrictive IPC and Content Security Policy.
- No external AI service calls.
- No telemetry without explicit authorization.
- No persistent raw audio or screenshots.
- No cross-project data leakage.
- No execution of imported document macros or scripts.
- Treat documents, transcripts, and screen content as untrusted data.
- Prevent prompt injection from controlling tools, paths, or project scope.
- Safe shutdown and capture cancellation on critical errors.

### 15. Laptop acceptance criteria

Release-critical tests:

1. RTX 4080 laptop is detected correctly.
2. Qwen3-VL 8B Q4 runs reliably within the measured memory budget, or an explicit validated fallback is documented.
3. Continuous transcription works while the 8B model generates answers.
4. No out-of-memory crash during a 90-minute meeting.
5. Audio capture works with headphones and external speakers.
6. Bulgarian and English transcription works.
7. Speaker IDs are editable.
8. Questions trigger relevant answers through the global shortcut.
9. No-question cases produce no answers.
10. Project-specific evidence is retrieved correctly.
11. Every displayed document citation resolves to a genuine source.
12. Screen context is incorporated when relevant and resources permit.
13. Risk indicators remain discreet.
14. Audio and screenshots are never persisted.
15. Unverified screen-sharing modes are handled safely.
16. Local history survives application restart.
17. AI functions operate without external inference access.
18. The Windows installer works on a clean target machine.

Initial performance targets:

- Median transcription lag: under 5 seconds.
- Manual answer completion: target under 45 seconds, with up to 60 seconds acceptable during initial validation.
- Stable 90-minute session.
- No unbounded audio buffers or GPU memory growth.
- Zero invalid citation IDs.
- Zero cross-project retrieval leakage.
- Zero generated answers on validated no-question examples.

Benchmark both model quality and resource consumption. Do not fabricate measurements.

### 16. Repository structure

Use:

- `apps/desktop` — Electron shell and mini window.
- `apps/web` — React dashboard.
- `services/api` — FastAPI and local AI orchestration.
- `services/capture-windows` — C# Windows integration.
- `packages/contracts` — Shared API and event definitions.
- `packages/ui` — Reusable interface components.
- `models/manifest` — Approved model metadata, digests, and configurations.
- `tests` — Unit, integration, end-to-end, and evaluation tests.
- `scripts` — Development, setup, benchmarking, and packaging.
- `docs` — PRD, architecture, security, data model, APIs, installation, troubleshooting, and architecture decisions.

Provide locked dependencies and reproducible Windows build commands.

### 17. Implementation milestones

**Milestone 0 — Laptop feasibility and architecture**

- Inspect actual RTX 4080 Laptop GPU memory and drivers.
- Validate Qwen3-VL 8B Q4 inference.
- Measure VRAM usage at multiple context sizes.
- Benchmark Whisper Medium in GPU and CPU configurations.
- Test concurrent transcription and LLM inference.
- Validate Windows Meet audio and selected-window capture.
- Establish repository structure, process contracts, and build approach.

**Milestone 1 — Desktop shell and dashboard**

- Electron application lifecycle.
- Browser dashboard.
- Mini window.
- Project CRUD.
- Session state machine.
- Global shortcut.
- Security and local API foundation.

**Milestone 2 — Document intelligence**

- File parsing and indexing.
- Local embeddings.
- Project isolation.
- Hybrid search.
- Citation validation and previews.

**Milestone 3 — Live meeting pipeline**

- Microphone and Meet audio.
- Whisper transcription.
- Speaker diarization.
- Transcript persistence.
- Audio-device recovery.

**Milestone 4 — Manual AI assistance**

- 90-second context snapshot.
- Explicit-question detection.
- Grounded answer generation.
- Source validation.
- Mini-window results.

**Milestone 5 — Screen and risk intelligence**

- Selected-window visual context.
- Change detection.
- Risk indicators.
- Sharing safety and capture exclusion testing.
- GPU scheduling under full concurrent workload.

**Milestone 6 — Packaging**

- Windows installer.
- Onboarding wizard.
- Model installation.
- Hardware profiling and local inference verification.

**Milestone 7 — Laptop release qualification**

- Complete functional evaluation.
- GPU/CPU performance profiling.
- 90-minute Google Meet tests.
- Security and privacy validation.
- Clean installer testing.
- Optional RTX 3090 Ti compatibility benchmark.

### 18. Codex execution rules

- Work one milestone at a time.
- Start with Milestone 0.
- Do not build the whole application in one pass.
- Do not change product requirements to simplify implementation.
- Do not use cloud inference as a workaround.
- Use the RTX 4080 laptop as the primary performance constraint.
- Retain the 8B model as the quality candidate until real benchmarks justify changing it.
- Prefer sensible CPU/GPU workload distribution over reducing the feature set.
- Create tests alongside implementations.
- Do not simulate core functionality in release builds.
- Report measured resource use and actual test results.
- Document technical tradeoffs and limitations.
- Do not mark untested functionality as complete.

### 19. First execution instruction

Begin with **Milestone 0 only**.

Before implementing the full application, verify that the laptop can run the proposed local AI workload.

Deliver:

1. Hardware detection report.
2. Installed runtime and compatibility report.
3. Qwen3-VL 8B memory and latency benchmarks.
4. Whisper Medium GPU-versus-CPU benchmark.
5. Concurrent transcription and generation results.
6. Windows Google Meet audio-capture feasibility results.
7. Selected-window capture feasibility results.
8. Proposed resource-scheduler design.
9. Final recommended laptop model configuration.
10. Repository foundation and automated checks.
11. Explicit pass/fail status for each feasibility test.

Stop after Milestone 0 and request approval before implementing the remaining milestones.

The goal is a reliable, fully local AI meeting copilot on the RTX 4080 laptop, with accurate project-grounded answers and uninterrupted meeting transcription.