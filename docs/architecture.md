# Milestone 0 architecture proposal

Status: proposed; laptop performance and Windows integration are unverified.

Electron/TypeScript owns process lifecycle, consent, tray, shortcuts and mini window.
React/Vite shares typed state through authenticated FastAPI REST/WebSocket contracts.
C#/.NET helper will own WASAPI audio and Windows.Graphics.Capture; Python probes here
are disposable feasibility tools, not the shipping helper. SQLite FTS5 and persisted
NumPy embeddings provide project-scoped hybrid retrieval in later milestones.
No frontend, API, retrieval, scheduler or meeting functionality is implemented in M0.

## Resource scheduler

One bounded heavy-generation slot, OLLAMA_NUM_PARALLEL=1; measure baseline display and
Chrome usage before admission. Start at 4096 context and 2048 MiB reserve. NVML/system
GPU telemetry plus Ollama /api/ps govern admission; sampled nvidia-smi usage is total
GPU usage, not a precise per-model allocation. Memory between samples can peak higher.
Keep continuous capture independent of inference workers. Timestamp and sequence all
PCM packets. Use bounded RAM queues; report overflow, never silently stop capturing.
ASR runs in a dedicated process in production. Benchmark CUDA int8_float16 Medium and
CPU int8 Medium before choosing. CPU is a candidate to preserve 8B GPU headroom, not a
validated recommendation. Priorities: capture > ASR > manual answer > retrieval > vision
> risk > diarization > indexing. Freeze background vision/risk during an answer.

Admission defers optional work and unloads embeddings via keep_alive=0; serialize model
switches and wait for observed release. Reject or defer requests when reserve is at
risk; bounded queues, cancellation, deadlines, visible degraded status. Reduce context
before choosing 4B; switch only with measured evidence or explicit user choice. CPU/GPU
hybrid selection must include transcript backlog and quality, not VRAM alone.

## Boundaries and build approach

Python 3.11/3.12 x64 for API and ASR; NVIDIA driver/CUDA/cuDNN compatibility must match
CTranslate2 on target. Ollama runs separately on loopback with local model cache.
.NET 8 Windows helper targets Windows 11 x64 with WASAPI and WGC interop. Electron,
React, Tailwind/shadcn and API packages remain scoped placeholders until M1 approval.
A fully resolved Windows dependency lock and tested .NET/Node build matrix remain
blocked on target setup; direct Python pins are not a reproducibility claim.
Future packaging bundles licensed runtimes, never unapproved model weights. Build
helper, API, dashboard, then Electron installer; clean-machine qualification is M6/M7.

## Privacy and security

Media stays in bounded RAM. Neither probes nor benchmark artifacts store raw audio,
screenshots, prompts, model answers or transcripts. Counts/timings and hardware metadata
only. Use synthetic audio generated in RAM for transport checks; use consented live
speech for ASR. No external inference, telemetry, cloud fallback, or automatic answers.
Treat captured content/documents as untrusted. Validate citations and project scope
before output in later milestones. Tab-only Meet sharing until preview-tested; content
protection is defense in depth. No invisibility guarantee.
