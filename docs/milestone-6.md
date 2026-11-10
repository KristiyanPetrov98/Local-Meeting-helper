# M6 implementation, packaging and qualification report

Date: 2026-11-09. M6 code and portable/package validation are implemented. **A Windows
Setup.exe has not been produced or installed in this Linux environment.** The actual
Windows installer build and clean-machine acceptance remain blocked/pending. M7 has
not been started.

## Features implemented

- A Windows x64 NSIS installer configuration, strict Windows packaging script and
  manual Windows build workflow, with self-contained backend/helpers and no required
  end-user Python, Node or .NET SDK. Data/models stay outside the install directory.
- Installed-resource discovery and a frozen executable that starts its own fixed
  parser/media/setup workers; existing source development remains supported.
- A first-run/reopenable wizard with hardware/dependency evidence, configuration,
  model license/access review, explicit downloads, protected local imports, integrity
  checks, live capture evidence, offline tests, device measurements and limited mode.
- Real Ollama pull clients, pinned Hub revisions, SHA-256 snapshots, token redaction,
  cancellation, single-operation admission and interrupted-install recovery.
- A consented short ASR/generation benchmark and explicitly reviewed measured profiles.
  Untested model files and blocked runtime checks cannot silently become verified.
- Runtime/license inventory collection, hash locks, packaging gates and regression tests.

## Files and components changed

New API modules: `runtime.py`, `launcher.py`, `model_assets.py`, `asset_worker.py`,
`check_worker.py`, `setup_checks.py`, `onboarding.py`, `setup_api.py`. Integrated with
`app.py`, `__main__.py`, `assistance.py`, `meeting.py` and `documents.py` to preserve
private worker entry points, cancellation, audio counters and session admission.

Desktop: new `apps/desktop/src/runtime.ts`, updated main process and native command
union. Web: new `SetupPanel.tsx`, dashboard/styles and generated OpenAPI/types.
Packaging: `electron-builder.yml`, `packaging/backend.spec`, `before-pack.cjs`, build
entry/notices/licenses, `requirements-packaging.in/.lock`, `package-lock.json`,
`scripts/package-windows.ps1`, `collect-notices.py`, `smoke-bundle.py`, and the manual
`.github/workflows/m6-windows-installer.yml`.

Tests: `tests/api/test_m6.py`, `tests/desktop/runtime.test.ts`, `tests/e2e/m6.spec.ts`,
`m6-package.spec.ts`. Existing M1–M5 tests and functionality remain. Architecture:
[m6-architecture.md](m6-architecture.md). Evidence: [m6-validation.json](m6-validation.json),
[m6-dependencies.json](m6-dependencies.json), [frozen smoke](m6-bundle-smoke.json).

## Tests executed

**244 automated tests passed, zero failed, zero skipped in the final Linux run.**

| Check | Result |
| --- | --- |
| Full API/parser/process/setup suite | 214 passed, including 32 M6 cases |
| Actual Electron/Playwright workflows | 12 passed, including wizard/import and packaged app |
| Vitest shell/rendering/packaging guards | 10 passed |
| Preserved M0 feasibility tests | 5 passed |
| .NET audio conversion/protocol tests | 3 passed |
| Contracts, type checks, production build, Python compilation, pip check | Passed |
| Both Windows helpers, self-contained x64 cross-publish | Passed |
| Linux frozen backend and real packaged desktop build | Passed |
| Frozen backend/parser/ASR-library/core checks outside checkout | Passed |
| Windows NSIS target attempted from this environment | Blocked by real-Windows-backend/full-runtime gate |

The packaged test launched the actual installed-layout app outside the repository,
with Python/Node absent from PATH and an invalid Python override. It started its
bundled API, indexed a real document through its bundled parser, resolved a citation,
used the native folder picker fixture and bundled asset worker, and shut down cleanly.
No real model weights were supplied; imported test weights are explicitly non-working
fixtures and remained inference-unverified.

API tests check protected import capability, fixed catalog and endpoint policy,
license/network acknowledgement, actual snapshot copy/hash/revision code, tampering,
symlink/traversal rejection, cancellation/recovery, token/exception redaction, model
cache avoidance, pull redirects/errors, idle/live guards, actual offline core worker
execution, measured-profile rules, manual/pause/stop preemption and explicit limited
completion. Hub/Ollama download protocol tests use labelled fixtures. The short
benchmark's positive tests simulate ASR/runtime evidence; they do not qualify hardware.

## Windows installer status and acceptance

The build input cannot be substituted across OS platforms: PyInstaller produces a
platform-specific Python/native runtime. `npm run package:win` was actually attempted;
it failed with **“A real Windows backend build with all runtime libraries is required.”**
That gate prevents shipping the Linux smoke backend as a Windows installer. There is
no fake or UI-only Setup.exe. The Windows script/workflow are ready to run on a real
Windows x64 build host; their Windows execution is not a passed result here.

| Criterion | Status |
| --- | --- |
| Wizard, actual diagnostics/actions and explicit blocked results | Passed on Linux Electron |
| Installed app uses bundled backend/workers without developer tools | Passed for the actual Linux package; Windows pending |
| Approved downloads/imports/checksums/cancellation | Real local import and protocol fixtures passed; actual host downloads blocked |
| Self-contained Windows helper binaries | Cross-build passed; Windows runtime unrun |
| Real Windows installer produced | Blocked in this environment; Windows build required |
| Clean-machine install/start/upgrade/uninstall | Unrun |
| Actual 8B + bilingual Whisper benchmark/profile | Unrun; fixture admission rules passed |
| Actual microphone, Meet and selected-window checks | Unrun; guided live evidence collection implemented |
| Offline real-model inference and quality | Unrun; missing dependencies correctly reported blocked |
| Signed release / sustained RTX 4080 qualification | Pending M7 |

## Blockers and remaining limitations

This environment is Linux, without nvidia-smi, an Ollama service or meeting-model
weights. Fresh requests to the Ollama registry and Hugging Face returned configured
proxy CONNECT 403. No real GPU memory, inference latency, bilingual accuracy or device
stability measurements are available. Missing measurements remain null/unrun.

The Linux smoke build intentionally omits the optional Windows diarization stack;
the Windows build requires those libraries and an actual import check. It must be
built/tested on Windows, including CUDA/cuDNN if GPU Whisper is selected. CPU ASR is
the starting path. Actual Community-1 config/checkpoint/runtime compatibility remains
untested; incomplete or nonlocal snapshots are rejected rather than auto-downloaded
at meeting time. Import checksums establish integrity, not signed upstream provenance.

The Windows candidate is unsigned; signing and SmartScreen/clean-machine verification
remain open. No model weights are redistributed except the licensed small runtime
VAD dependency. License texts/inventory are review inputs, not a completed legal or
security audit. Native helpers still target the existing pinned .NET 8 SDK/runtime;
.NET 8 support ends 2026-11-10, so update/requalify that runtime before a production
release rather than treating this alpha candidate as release-ready.

A short benchmark uses synthetic neutral generation with live speech and periodically
observed GPU-wide memory. It is not a ninety-minute test, a per-kernel peak allocation
measurement or automatic speech-quality scoring. The user reviews accuracy before
applying. Profile fingerprints bind model/configuration evidence; driver/runtime
updates still require manual reruns. No automatic 4B or larger-context configuration
is enabled without target measurements. Capture exclusion and Meet picker enforcement
remain unverified and unchanged from M5.

## Build the Windows candidate

On a Windows x64 build machine with Python 3.12, Node 24 and .NET SDK 8.0.427:

```powershell
.\scripts\package-windows.ps1
```

Or commit the source to the repository and manually run **M6 Windows installer
candidate** in GitHub Actions. The workflow only uploads an unsigned candidate and
notices; it does not publish a release. These build instructions are not end-user
requirements. The script installs hash-locked build dependencies, builds both native
helpers self-contained, freezes the full backend, runs the bundle smoke and invokes
NSIS with `--publish never`. It writes the installer and SHA-256 sums under `release/`.

Do not bypass the Windows PE/runtime gate to reuse the Linux bundle. Review notices,
model access/redistribution conditions and signing before distributing a candidate.

## Manual test on a clean Windows 11 RTX 4080 laptop

1. On the build host, produce the candidate using the script/workflow above. Verify
   its SHA-256 and signing status. In a clean Windows 11 x64 test account, install it
   as a standard user. Confirm start-menu/desktop shortcuts and selectable per-user
   location. Python, Node and .NET SDK must not be installed as prerequisites.
2. Launch the app. The first-run wizard must open without blocking existing projects.
   Inspect actual RAM/CPU/disk/GPU/runtime evidence. Keep 8B, context 4,096 and Whisper
   Medium CPU int8 initially, with the provisional 2 GiB reserve/8 GiB job budget.
3. Install local Ollama from the official link. Start it with one parallel request
   (`OLLAMA_NUM_PARALLEL=1`) and loopback binding; the source helper
   `scripts/start-ollama.ps1` demonstrates those settings. Review the official model
   license/access pages, explicitly allow each download, and install generation,
   embedding, selected Whisper and optionally Community-1 assets. Use a token only
   in the local password field for gated access; do not share it in chat/logs.
4. Test approved local import through the desktop folder picker. Verify checksums.
   Repeat without replacement: no duplicate install should run. Explicitly replace
   a test snapshot, cancel an operation and restart mid-operation; previous working
   assets should recover and incomplete operations must not appear successful.
5. Run offline self-tests with all required assets present. Inspect every check rather
   than the operation's completed status. Then disconnect external networking (leave
   loopback available) and repeat. Confirm actual generation, embeddings, parser and
   local speech/diarization loading, not just metadata presence. Silence inference
   proves loading only; it does not establish speech recognition accuracy.
6. Configure the real mic and Meet playback device below the wizard, confirm consent,
   declare sharing mode, select an application window, and explicitly enable capture.
   Speak both languages from both sides, inspect the transcript and window preview,
   and use **Inspect live capture evidence**. Follow the M5 Meet preview workflow;
   actual exclusion must still say unverified.
7. While that test session stays active, keep bilingual speech flowing and run the
   device benchmark. Inspect its actual latency, memory trace, ASR lag/gaps/drops and
   generated synthetic output. Test manual shortcut, pause and stop preemption. A
   failed/interrupted run must not produce a usable profile.
8. Stop, review accuracy, then apply the matching measured profile. Change a model or
   configuration and verify stale/failed evidence cannot be applied. Finish with
   incomplete tests only by explicitly selecting limited mode; release qualification
   must remain false. Restart and verify acknowledgement, settings and project history.
9. Test install path with spaces, upgrade, cancel installation, backend/helper failure,
   offline startup, and uninstall/reinstall. App data/models must be preserved on
   uninstall; remove them separately only if intentionally erasing local history.
10. Finally run M0/M5 laptop workload protocols and M7's eventual full integration /
    ninety-minute release qualification. Do not infer those passes from this wizard.

If native dependencies fail, use the official Microsoft Visual C++ x64 runtime and
NVIDIA driver/runtime documentation. GPU Whisper additionally needs the compatible
CTranslate2 CUDA/cuDNN runtime; CPU Whisper does not require that CUDA setup. Native
.NET libraries are included by the candidate build. Dependency/runtime issues must
remain visible and block the corresponding check instead of prompting fake success.

## Reproduce the cloud checks

Use the existing development locks plus `requirements-packaging.lock` and `npm ci`.
Run the repository API/Vitest/type/build/contracts tests. For the Linux packaging
smoke (not a Linux distribution promise):

```bash
.venv/bin/python -m PyInstaller --noconfirm --distpath build/backend --workpath build/pyinstaller packaging/backend.spec
.venv/bin/python scripts/collect-notices.py
.venv/bin/python scripts/smoke-bundle.py --backend build/backend/pm-copilot-api/pm-copilot-api --web apps/web/dist --output docs/m6-bundle-smoke.json
npm run package:linux-smoke
PM_PACKAGED_APP="$PWD/release/linux-unpacked/pm-copilot" npm run test:e2e
```

Create the native helper resource directories first (the cloud cross-built real Windows
helpers there). GUI checks require an X display and installed Chromium. Without a built
package, its dedicated Playwright case is explicitly skipped. The final cloud run
included that package case and had zero skips. No Windows build/workflow was remotely
run or published in this chat.
