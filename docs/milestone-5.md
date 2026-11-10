# M5 implementation and qualification report

Date: 2026-11-09. M5 source and portable integration are implemented. Windows capture,
real vision/risk quality, Meet exclusion and RTX 4080 concurrency remain unqualified.
Work stops at M5; M6/M7 have not been implemented.

## Features implemented

- A separate Windows.Graphics.Capture helper with explicit HWND/PID selection,
  visible capture, source identity checks, resizing and bounded private-pipe frames.
- RAM-only previews, lightweight change detection, 1.5-second stability, ten-second
  background rate limit, recent visual context for M4 and graceful capture failure.
- Opt-in background potential-risk hints for all seven v1.1 categories, inspectable
  transcript/document evidence, project/session isolation, source revalidation and expiry.
- A shared inference scheduler with manual priority/preemption, actual telemetry code,
  residency accounting, configurable reserve, bounded CPU fallback, optional-work deferral,
  pressure cancellation and confirmed primary-model unloading.
- Declared-sharing acknowledgement, safe companion visibility paths, preview instructions
  and content protection requests. Session startup preserves broader-mode restrictions.
- Setup/launcher scripts, contracts, automated tests and technical documentation.

## Components changed

New: `services/screen-windows/`, API modules `resources.py`, `screen_native.py`, `screen.py`,
`visual.py`, `sharing.py`, `m5_api.py`, React `ScreenPanel.tsx`, `tests/api/test_m5.py`,
`tests/e2e/m5.spec.ts`, `tests/desktop/risk-ui.test.ts`, `scripts/setup-m5.ps1` and
`scripts/start-ollama.ps1`.

Integrated with existing `app.py`, `__main__.py`, `assistance.py`, `assistance_store.py`,
`generation.py`, `briefing.py`, `meeting.py`, Electron main, React main/styles and
OpenAPI/generated contracts. Existing M3 subprocess regression now checks packet/ASR
progress under a manual resource lease. Existing desktop tests explicitly acknowledge
sharing mode. READMEs and CI build steps were updated; no application installer was added.

See [architecture](m5-architecture.md), [dependency evidence](m5-dependencies.json) and
[machine-readable validation](m5-validation.json).

## Tests and measured results

Final Linux results: **205 passed, zero failed, zero skipped**.

| Automated check | Result |
| --- | --- |
| Complete API/parser/subprocess suite | 182 passed, including 45 M5 cases |
| Real Electron/Playwright workflows | 9 passed |
| Vitest shell and risk-rendering checks | 6 passed |
| M0 feasibility regressions | 5 passed |
| .NET audio tests | 3 passed |
| Windows screen helper locked restore / Release cross-publish | Passed; zero warnings/errors |
| Type checks, production build, schema consistency, Python compilation, pip check | Passed |

An audio-retry integration regression found in final review was corrected and now has
an explicit test proving that retry leaves the existing screen/risk workers running.
The native guard also passes a simulated connection-failure test and uses one bounded
visibility check at a time with a one-second timeout.

The test scope is:

- Full API/parser/pipeline regression suite, including M5 frame, scheduler, preemption,
  preview, sharing, scoping, risk validation, expiry and changed-source cases.
- Real Electron startup and all dashboard/companion workflows on a Linux Xorg display,
  including native hotkey delivery and actual native window visibility under unknown,
  tab and broader modes. Browser/API sharing changes hide the real companion. Starting
  a session in broader mode does not bypass the guard. Settings survive restart while
  sharing acknowledgements reset.
- Vitest shell checks plus positive risk/evidence rendering and escaping of hostile
  transcript/document HTML, M0 portable tests, and existing .NET audio tests.
- Pinned Windows SDK restore and Release win-x64 cross-publish of the new helper,
  TypeScript/build/contracts, Python compilation and dependency consistency.

Portable capture/telemetry/generation tests use explicit in-process fixtures. They
process real synthetic PNG/JPEG bytes in RAM and real SQLite/FTS sources. NVIDIA CSV
and Ollama residency/unload/multimodal payloads run through the real clients with test
transports. They do not establish that an RTX 4080 or WGC actually ran. The M3 regression
passes audio packets through actual subprocess pipes while a manual scheduler lease
is active; its ASR/capture subprocesses are labelled fixtures.

The actual cloud telemetry probe reports no nvidia-smi, no Ollama CLI, no resident
models and no GPU measurements. The configured model-registry proxy again returns
CONNECT 403. **No real-model latency, RTX 4080 VRAM or continuous Whisper/vision
stability measurements are available.** Null measurements are not zero latency.
The helper compiled with zero warnings/errors; its Windows COM/D3D/WGC execution is
not a passed capture test. PowerShell scripts were not executed on this Linux host.

## Acceptance criteria

| Criterion | Status |
| --- | --- |
| Actual app starts and existing M1–M4 workflows function | Passed on Linux Electron |
| Window-only transport, frame bounds and scoped preview | Portable fixtures passed; real Windows capture unrun |
| Stability/rate limit, stale/wrong-source rejection and capture-failure isolation | Portable tests passed |
| Manual priority, single-flight scheduling, optional deferral and CPU fallback | Portable tests passed |
| Real NVIDIA parser / Ollama residency and unload client | Fixture protocol tests passed; actual GPU unrun |
| Risk categories/evidence/expiry, no automatic meeting answers or saved unseen risks | Portable tests passed; model quality unrun |
| Native companion hidden for declared unknown/broader modes | Real Linux Electron test passed |
| Windows content-protection exclusion and actual Meet preview | Unrun; exclusion explicitly remains unverified |
| RTX 4080 8B + Whisper + screen workload stability and latency | Unrun; requires laptop |
| M5 Windows helper | Cross-build passed; runtime acceptance open |

No unrun hardware criterion is marked verified. M5 is ready for laptop testing, not
release qualification.

## Remaining limitations

The 8,192 MiB generation allowance is provisional, not a measured model allocation.
Admission and two-second sampling cannot prevent every transient GPU spike. CPU
fallback retains 8B and may be slow or contend with CPU ASR; it must be measured.
Multiple NVIDIA GPUs currently use the conservative CPU/deferred path. Server-side
cancellation timing and external Ollama clients are outside the application's lock.
Use the supplied launcher or configure Ollama with one parallel request.

The grayscale threshold and scaled image size may miss small text changes; no OCR was
added. Fresh matching frames can reaffirm a prior observation, but changed/stale/closed
sources invalidate it. Only a short observation goes into manual context; there are no
persisted screenshots to inspect later. Model-generated hints are tentative, not proven
risks, semantic entailment or guaranteed prompt-injection protection. They expire and
are never saved by default. Unavailable/changed evidence is removed from display.

Sharing protection depends on the user's truthful declaration before changing Meet's
picker. Native polling can take roughly 250 ms plus a local request. The app cannot
observe or enforce the picker and cannot guarantee invisibility during screen/window
sharing. Both content-protection calls and actual Windows rendering need laptop checks.
Tab sharing should select the intended content tab, never the Copilot dashboard tab.

## Manual test on the Windows 11 RTX 4080 laptop

1. Complete the existing M3 audio/Whisper/Community-1 setup. Install Node 24, Python
   3.12 x64, .NET SDK 8.0.427 and local Ollama, then run from the repository:

   ```powershell
   .\scripts\setup-m5.ps1
   ```

   This reuses the M4 Python lock (Pillow, httpx and language detection already included)
   and builds the Windows screen helper. It does not install an application installer.
2. Quit an existing Ollama tray server, then run `scripts/start-ollama.ps1` in a separate
   terminal. Install `qwen3-vl:8b-instruct-q4_K_M` and `qwen3-embedding:0.6b` if missing.
   Retain the primary 8B, 4,096-token profile; do not substitute 4B before measuring 8B.
3. Run `npm start`. Create/select Alpha and import representative project documents.
   In **Screen, sharing & resources**, choose **One Chrome tab** (or no screen sharing),
   acknowledge and Apply. Unknown/broader modes must keep the companion hidden.
4. Refresh windows and select a harmless test editor/document. Confirm Copilot windows
   are absent from the selector. Start a consented test session, verify the actual
   sharing mode, and explicitly enable audio, selected-window capture and optional risks.
   Confirm the Windows capture border and increasing frame count. Open the in-memory
   preview and verify only the selected window is present. Preview again after a change.
5. Edit the selected window, stop changing it for at least 1.5 seconds, and observe
   analysis after the ten-second rate allowance. Repeated unchanged frames must not
   cause repeated inference. Change another window: it must not become the source.
   Resize, move between monitors, minimize and close the selected window. A failure
   must clear preview/context and leave audio/transcription usable; reselect explicitly.
6. Ask a confirmed English/Bulgarian question, then trigger M4. Check recent screen
   context when available and valid project citations. Screen content alone must never
   acquire a document citation. Trigger manual work during a background job and keep
   speaking: optional work should preempt/defer while transcript timestamps advance.
7. Use a consented scenario with a missing dependency, unresolved requirement and
   documented contradiction. Inspect the risk indicator, exact transcript/document
   evidence and tentative wording. Verify no automatic answer/history entry appears.
   Delete/revise a cited source and check that the finding disappears. Switch projects,
   pause/stop and restart: no frame or finding may carry over. Findings expire after
   ninety seconds without a successful refresh.
8. In Meet choose **Present now → A tab**, select the intended content tab, and inspect
   Meet's own preview plus a second participant's view. Verify Copilot is absent. Record
   the user preview acknowledgement, while exclusion still reads unverified. Before
   choosing any entire-screen/window mode, declare **Window or entire screen** here;
   confirm the mini is hidden and hotkeys/Open companion cannot show it. Repeat from
   the browser dashboard and start a new session while broader mode is still selected.
9. Test CPU mode and insufficient-resource deferral, then return to the measured GPU
   profile. Review free/total memory, residency and events via the authenticated resource
   API. Changing source/settings while paused must not prevent audio from resuming.
10. With all assets installed, disconnect external networking and repeat the core flow.
    Keep loopback available. Check the test profile for new media files: none should be
    created. Stop the app and verify its audio/screen child processes exit.

For qualification, run at least thirty minutes of continuous bilingual speech while
changing the selected window and issuing cold/warm manual requests. Record actual
hardware/model digests, nvidia-smi memory samples, model load/evaluation times, answer
latency, frame/analysis counts, ASR queue/lag/gaps/drops and human-scored visual/risk
accuracy. Begin with CPU Whisper Medium int8 and CPU diarization. Only evaluate GPU
Whisper after establishing that baseline. Tune the budget/reserve from measurements
and keep the initial approximately 2 GiB reserve target. Do not mark concurrency,
sharing exclusion or model quality passed until these tests run on the laptop.
