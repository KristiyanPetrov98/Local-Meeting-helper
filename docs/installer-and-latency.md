# 0.2 — installer automation and transcription latency

2026-11-10. This update addresses the laptop user's repeated terminal setup and slow visible transcription. The retrieval-stall fix is already included. Source changes and portable tests do not establish a working Windows installer or real Whisper latency; those remain pending the Windows build and laptop retest.

## Intended installed experience

1. Download a successful Windows installer candidate from the repository's **Windows installer candidate** Actions run, unzip the artifact and run `PM-Copilot-0.2.0-x64-Setup.exe`.
2. Setup installs the app and bundled runtimes. Windows can request permission for the signed Microsoft C++ runtime when it is missing, and can require a reboot. The PM Copilot wrapper is currently unsigned; signing/distribution review remains a release gate.
3. Launch PM Copilot from the Start menu. It starts its bundled local Ollama engine in the background, with loopback binding and one parallel request. No PowerShell, Python, Node or .NET SDK is required on the installed machine. Python/native worker launches and recurring NVIDIA probes now explicitly use the Windows no-console flag, while retaining the separate background-priority policy.
4. Acknowledge the model licenses and one-time downloads, then click **Set up this computer**. This reuses the exact installed Ollama models, verifies an existing managed Whisper snapshot or downloads it, then runs actual offline runtime checks. Results distinguish required-runtime readiness from full qualification. Downloads are several gigabytes and can take time. The app never silently enables microphone/screen capture.
5. Select the microphone and Meet playback endpoint and start a consented session. Community-1 remains available as an optional refinement setup because its upstream model has access conditions. Existing document/RAG, history, hotkey, speaker-editing, vision and qualification functions remain.

Models are installed once after network/license acknowledgement, rather than making the installer carry all pretrained weights. Offline inference remains local. The installed engine is not downloaded again on every launch. An existing local Ollama server is reused and is not killed on application exit. When PM Copilot starts its own server, it shuts down that server and its runners on exit. Source launches on Windows can also start the installed Ollama executable automatically.

## Build and supply-chain boundaries

The Windows packaging script now stages:

- The official Ollama Windows x64 standalone archive. Its release asset must publish a SHA-256 digest; the download is checked before extraction. Version, archive hash and executable hash are recorded. Archive origins are fixed, path escapes/symlinks are rejected, and original runtime license content is included.
- A FFmpeg-Builds (formerly BtbN) FFmpeg **7/8 LGPL shared** Windows build for TorchCodec. Its release asset digest is checked, archive paths are bounded, the executable's version/configuration is checked, and accompanying license/documentation/build metadata are preserved. The frozen entry point registers the bundled FFmpeg DLL directory before model-worker imports. GPL/nonfree build flags are rejected. This is a third-party build; redistribution/source/license review remains required before public release.
- The official Microsoft Visual C++ x64 redistributable. Windows must validate its Authenticode signature and Microsoft publisher. The installer checks the installed runtime and runs the signed prerequisite when needed. The build records its version and content hash.

Builds choose the stable official Ollama release/current compatible FFmpeg build at packaging time and record exact downloaded identities. This is not a byte-reproducible pinned binary build. The packaging gate rejects modified Ollama or Microsoft runtime executable hashes. Python/.NET/Electron packaging remains in the existing pipeline; actual frozen pyannote imports and bundled-worker smoke checks must pass before NSIS packaging. The production process supervisor also starts the actual staged Windows Ollama binary on an isolated smoke-test port, checks its version, shuts down its owned tree and verifies that the port closes. Packaging requires that Windows smoke report; model inference is not claimed by a version check.

The Windows workflow now runs automatically for implementation/build changes pushed to main, as well as manual dispatch. It uploads an installer candidate on success and build diagnostics even on failure. **A diagnostics artifact alone is not an installer.** This chat environment cannot call `api.github.com` (network proxy CONNECT 403) and its GitHub CLI credential is invalid; Windows execution and build status cannot be asserted from a successful Git push alone. No release is published by this workflow.

## Transcription changes and measurement limits

Previously, every source collected a four-second window before decoding, even when a short spoken phrase had already ended. The new collector can submit after at least one second of accumulated audio and 600 ms of low-energy quiet. Continuous speech keeps the four-second window and overlap. Discontinuities reset the endpoint history. The Whisper model, int8/float16 choice and beam-size quality defaults are not silently reduced.

The deterministic audio test submits 1.2 seconds of synthetic voice plus 600 ms of silence at **1.8 seconds**, versus waiting for a four-second batch. **This is a collection-time measurement, not 1.8-second Whisper or end-to-end transcription latency.** Energy endpointing can miss quiet boundaries in noisy input and does not replace a full speech VAD. The real 10–15-second report has not been reproduced on this Linux host or proved resolved.

The live pipeline now records batch duration, queue wait, actual decoder duration, real-time factor, actual CPU/CUDA worker selection and delay from recognized word end to transcript delivery. These are visible under **Audio & transcript → Transcription performance**. A native Save dialog exports **Download performance report** without opening a terminal; it excludes transcripts, documents, media, credentials and project names. Qualification exports also use the native Save dialog in Electron. Browser users retain browser downloads.

If decoding is slow, reducing collection delay alone will not solve it. CUDA Whisper selection, native CUDA-library compatibility, bilingual quality, 8B concurrency and GPU headroom still need the real laptop. There is no newly validated smaller-model fallback, no automatic quality reduction and no confirmed sub-five-second target-hardware result.

## Tests and acceptance

See `installer-latency-validation.json` and accompanying API/Electron results for the final executed counts. New tests exercise:

- An actual owned engine subprocess starting once under concurrent requests and stopping; existing external service preservation; missing-runtime failure.
- Setup consent gating, exact model preparation order, existing snapshot verification and failed required checks retaining a failed readiness verdict.
- Quiet-boundary batching, continuous speech, silence-only input and discontinuity handling.
- Rejection of modified staged runtime executables.
- Real Electron setup controls and a native Save dialog writing the actual sanitized performance report.

The Windows download/staging scripts, vendor signature validation, NSIS prerequisite execution, frozen FFmpeg/pyannote integration, clean-machine install and actual Windows server process-tree termination have **not** run on this Linux host. Windows CI/laptop evidence is required. GPU/Whisper inference, bilingual accuracy, 90-minute stability and signing remain unverified. No build or test presence is counted as a hardware pass.

## Laptop retest without terminal/provider management

Use the successful Actions installer candidate when available. Quit the old source application before launching the installed version. Keep the same Windows user account so existing model caches can be reused. In the app, run setup once, inspect any failed runtime check, then use a consented session to test a short question followed by a pause and a continuous passage. Confirm transcript text and request/cancel controls remain responsive. Save the performance report from the app after observing the delay. That report is the evidence needed to separate slow decoding from collection/queue/UI delay before tuning the GPU profile.
