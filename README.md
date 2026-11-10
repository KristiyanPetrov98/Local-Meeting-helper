# PM Copilot

A local-first meeting workspace for Windows 11 and the RTX 4080 Laptop GPU.
**M1 through M7 implementation code is present; release qualification is blocked.** Portable integration, security, dependency and startup checks pass. The Windows installer build/install and real laptop acceptance remain pending; see the M7 report. M3 Windows/live-model acceptance is unverified; see the
[M3 implementation and Windows test guide](docs/milestone-3.md).

M1 provides Electron lifecycle/tray, a React dashboard and floating companion, persistent
project CRUD/selection, consent-gated session states, configurable global shortcuts,
and one authenticated FastAPI/SQLite state source shared with a local browser dashboard.
M3 adds a native WASAPI helper, isolated local Whisper/Community-1 workers, audio settings,
project-scoped transcript history, and speaker editing. Capture is explicitly opt-in.
M2 adds project document ingestion, local retrieval and verifiable source citations.
M4 adds manual question detection, bounded local Ollama briefings and response history.
M5 adds a Windows selected-window helper, ephemeral vision/risk analysis, declared-sharing
safeguards and resource scheduling. M6 adds installer build scripts and a guided setup wizard. A Windows Setup.exe has not been produced in this Linux environment. Real Qwen3-VL quality and RTX 4080
concurrency remain unverified; see [M4 results and manual tests](docs/milestone-4.md).

M0 hardware feasibility remains unverified; its probes and reports are preserved.
There is no RTX 4080 performance or release-readiness claim.

## Final validation and target-laptop qualification

See [M7 results and manual qualification](docs/milestone-7.md) and
[the release checklist](docs/release-qualification.md). The setup wizard now has an
explicit 90-minute metrics recorder under **Device benchmark**. It never certifies a
release from a short check or missing evidence. Native helpers now target .NET 10 LTS.

## Build and test M6 setup

The dashboard now includes **Set up PM Copilot** for actual dependency checks, approved
model installation/import, offline tests and a short live-device benchmark. Missing
requirements stay blocked; limited mode must be acknowledged explicitly.

On a Windows x64 build host, run `scripts/package-windows.ps1` or dispatch the manual
Windows installer workflow. The packaged app bundles its backend/runtime/helpers;
end users do not need Python, Node or a .NET SDK. **No Windows Setup.exe is included in
this cloud result.** See [M6 build status and clean-machine tests](docs/milestone-6.md).

## Test M5 screen and resource integration

Complete M3 audio setup, then run `scripts/setup-m5.ps1` on Windows. Start local Ollama
with `scripts/start-ollama.ps1`, then `npm start`. Select a project, explicitly declare
sharing mode, select an application window and enable capture/risks in the consented
session dialog. See [M5 acceptance and laptop tests](docs/milestone-5.md).

M5's Windows helper cross-builds and portable tests pass. Real WGC capture, Meet
exclusion, visual/risk accuracy and RTX 4080 concurrency are **unverified**. The default
2 GiB reserve and 8 GiB primary-job budget require target measurements. No images or
risk findings are saved by default; an unsupported sharing mode keeps the mini hidden.

## Test M4 manual assistance

Run `scripts/setup-m4.ps1` in PowerShell. For live audio also complete the existing
M3 setup below. Install local Ollama, set `OLLAMA_NUM_PARALLEL=1` before starting
its server, and pull `qwen3-vl:8b-instruct-q4_K_M`. Semantic retrieval additionally
uses `qwen3-embedding:0.6b`; keyword fallback is explicit when it is unavailable.

Run `npm start`, select a project, import evidence, and start a consented session with
Whisper capture enabled. Ask a clear English/Bulgarian question, wait for its confirmed
transcript, then press Ctrl+Shift+Space or **Request briefing**. No explicit question
means no generated answer. The [M4 guide](docs/milestone-4.md) covers citations,
cancellation, offline checks, missing dependencies, and required Windows/GPU validation.

## Test M2 document intelligence

Python 3.12 x64 and Node 24 are required. From the repository root:

```powershell
.\scripts\setup-m2.ps1
npm start
```

Select a project, add files in **Project knowledge**, and use Keyword search / source
previews. For semantic search install local Ollama and run
`ollama pull qwen3-embedding:0.6b`, then Refresh model status and Reindex.
See [M2 dependencies and test guide](docs/milestone-2.md). Real-model semantic quality
is unverified here; the environment blocks model-registry access. No fake vectors or
cloud inference are used when the model is missing.

## Test M3 on the Windows laptop

Install Node 24, Python 3.12 x64 and .NET SDK 10.0.403, then from the repository root:

```powershell
.\scripts\setup-m3.ps1
.\.venv\Scripts\python scripts/download-whisper.py --model medium
npm start
```

Use **Audio & transcript** to select the same microphone/output as Google Meet and save
the settings. Create/select a project, start a session, confirm consent and explicitly
check **Enable local audio capture and Whisper transcription**. See the guide above for
Community-1 assets, CPU/GPU testing, device recovery and limitations. Model installation
uses the Internet once; inference uses only local assets. Do not treat portable tests
or cross-built binaries as proof of live Windows capture.

## Develop on Windows (PowerShell, repository root)

Prerequisites: Python 3.12 x64 and Node >=22.12 (Node 24 tested on Linux).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-dev.lock -r services/api/requirements-assistance.lock
npm ci --ignore-scripts
node node_modules/electron/install.js
npm run build
npm start
```

The explicit Electron install invokes its official downloader and checksum validation.
If your corporate proxy requires Node 24's environment-proxy support, set
`$env:NODE_USE_ENV_PROXY = '1'` for the installer. Keep TLS/checksum validation enabled.
Application operation after installation requires no Internet or AI runtime in M1.
The same setup on Linux uses `python3 -m venv .venv` and `.venv/bin/python`.

Electron automatically launches the API on an OS-assigned **127.0.0.1** port. The token
is generated per launch and passed privately to the child process. Data lives in
Electron's OS userData directory; override with `PM_COPILOT_DATA_DIR` for a test profile.
Override `PM_COPILOT_PYTHON` with an absolute interpreter path only when required.
Open the browser dashboard from **Desktop settings → Open in browser**. Do not share
its initial fragment link: it contains a temporary authentication capability, removed
from the address bar immediately after loading. A new app launch requires reopening it.

## Checks

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m pytest tests/api -q
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Run contract generation in an activated Python virtual environment using `npm run contracts`.
Linux Electron E2E needs an X display; see [M1 report and manual tests](docs/milestone-1.md).
Windows commands are provided for reproduction, **not claimed as executed on Windows**.

## Documentation

- [Specification v1.1](docs/specification-v1.1.md)
- [M7 results, acceptance and manual tests](docs/milestone-7.md)
- [M7 security and architecture decisions](docs/m7-architecture.md)
- [Release qualification procedure](docs/release-qualification.md)
- [M6 packaging/setup report and Windows build instructions](docs/milestone-6.md)
- [M6 architecture](docs/m6-architecture.md)
- [M5 implementation, qualification and manual tests](docs/milestone-5.md)
- [M5 architecture](docs/m5-architecture.md)
- [M4 implementation, acceptance and manual tests](docs/milestone-4.md)
- [M4 architecture](docs/m4-architecture.md)
- [M2 implementation and dependency report](docs/milestone-2.md)
- [M2 architecture](docs/m2-architecture.md)
- [M3 implementation and Windows test guide](docs/milestone-3.md)
- [M3 architecture](docs/m3-architecture.md)
- [M1 implementation and acceptance report](docs/milestone-1.md)
- [Current architecture](docs/m1-architecture.md)
- [Laptop benchmark procedure](docs/benchmarking.md)
- [Windows capture feasibility protocol](docs/windows-capture.md)

Use the existing checkout; task environments are already isolated. Preserve M0 probes
and hardware constraints. M3 was implemented before M2 at the user’s request; both now exist. M4 reuses both stages. Preserve their unverified hardware/model checks before advancing.
