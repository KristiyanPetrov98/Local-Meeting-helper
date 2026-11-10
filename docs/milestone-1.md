# M1 implementation and acceptance report

Validated on 2026-11-06. **M1 functionality is implemented and validated on Linux.
Windows-native acceptance is pending; this is not laptop or release qualification.**
Stop here before M2. No document/AI/audio/vision functionality is simulated.

## 1. Features implemented

- Electron single-instance lifecycle, owned Python child with readiness handshake,
  tray actions, close-to-tray and explicit safe quit.
- React/Vite/TypeScript/Tailwind dashboard and a shared Radix/CVA button primitive.
- Always-on-top, draggable, collapsible, dismissible companion with position retention
  and display-work-area recovery. Dashboard can reopen the companion; the companion
  can reopen the dashboard.
- Persistent SQLite project create/rename/select/delete and recent session history.
  Confirmation for destructive deletion; database cascade limited to that project.
- Start/pause/resume/stop session state with consent and sharing acknowledgement UI.
  One live session; active-project switching/deletion blocked. Stale project starts
  rejected; project dialogs retain their original target across external changes.
- Shared authenticated FastAPI REST/WebSocket state for both native views and browser
  dashboard. Reconnect with capped backoff, bounded snapshot queue, revision ordering
  and disconnected-control disabling. Browser launch via desktop settings.
- Configurable global shortcut, registration/conflict reporting, previous-binding
  retention, native-status propagation. Hotkey opens the companion; no AI answer yet.
- Per-launch authentication, exact Host/Origin checks, CSP, sandboxed/context-isolated
  renderers, narrow IPC, permission denial, blocked external renderer navigation.
- Generated OpenAPI/TypeScript contracts, locked JS dependencies and hash-pinned Python
  runtime/dev dependencies, build scripts and future CI workflow definitions.

## 2. Files and components changed

| Area | Files / responsibility |
|---|---|
| Desktop | apps/desktop/src/main.ts, preload.ts, shortcut.ts, bounds.ts |
| Web | apps/web/src/main.tsx, client.ts, styles.css; index.html and vite.config.mts |
| API / database | services/api/pm_copilot/{app,store,__main__}.py and requirements locks |
| Shared contracts / UI | packages/contracts/openapi.json, src/*; packages/ui/src/button.tsx |
| Build / tests | package.json, package-lock.json, tsconfig.json, vitest.config.mts, playwright.config.ts; scripts/build-desktop.mjs, export-openapi.py, test-x11-shortcut.py |
| Automated suites | tests/api/*, tests/desktop/shell.test.ts, tests/e2e/m1.spec.ts |
| Documentation / CI | README.md, component READMEs, docs/m1-architecture.md, this report, .github/workflows/m1-checks.yml |

Existing M0 probes, specification, hardware constraints and evidence were preserved.
The checkout was already an unborn repository with untracked M0 files at audit; work
remains in the workspace, without a commit or push created by this task.

## 3. Tests executed and results

Actual host: Linux x64, Python 3.12.14, Node 24.22.1, Electron 45.2.3, system Chromium,
Xorg dummy display :99. No Windows machine or RTX 4080 was attached. No --no-sandbox
flag was used for Electron. The API and native GUI tests required execution outside
the command sandbox because it prevented local event-loop/display communication.

| Executed command/check | Result |
|---|---|
| Python unittest discovery (existing M0 checks) | **5 passed**, 0 failed |
| pytest tests/api from a clean hash-lock environment | **8 passed**, 0 failed |
| npm test (Vitest shell/shortcut/bounds) | **4 passed**, 0 failed |
| Playwright Electron + browser integration | **3 passed**, 0 failed (final run 8.9 seconds) |
| npm run typecheck | PASS |
| npm run build (production web + desktop bundles) | PASS |
| npm run contracts + checked-in schema consistency test | PASS |
| Python py_compile (API and M0 probes) | PASS |
| npm ci --ignore-scripts + explicit verified Electron install | PASS |
| Fresh Python install with --require-hashes + pip check | PASS; no broken requirements |

All 20 tests above actually ran; none were skipped. Initial API WebSocket fixture
and E2E window-selection failures were corrected and rerun. The tests now select the
dashboard by URL, since either native window can finish loading first. An API test also
asserts the checked-in OpenAPI schema matches the implementation.

E2E test 1 exercises real project CRUD, browser authentication/fragment cleanup,
three-view session synchronization, mini collapse/expand, shortcut configuration and
actual conflict rejection, renderer preferences/Node isolation, restart persistence and
project deletion. With PM_TEST_X11_INPUT=1 it sends a real XTest Ctrl+Shift+P sequence
and confirms the companion receives the callback. This flag **was set** for the final
run; that proves Linux X11 delivery, not Windows delivery.

E2E test 2 starts a live shell session, quits Electron, verifies the listener closes,
then restarts and observes a stopped session. E2E test 3 changes project selection
externally while rename/start dialogs are open and checks no operation silently crosses
the project boundary. API tests separately check interrupted-session recovery and
foreign Host/Origin/unauthenticated rejection.

No artificial wait-for-port check substitutes for the actual UI/API workflows above.
CI YAML has been added but no remote GitHub Actions run was triggered or verified.

## 4. Remaining bugs and limitations

- No known failing automated M1 check remains. Native Windows behavior has not run:
  shortcut conflicts/delivery, tray visibility, content protection, monitor detach/move,
  Python child shutdown under Windows, and installation from the locks need target tests.
- Two-monitor bounds logic is unit-tested; physical two-monitor behavior is unverified.
- Tray commands are implemented; actual tray-menu click behavior is a manual check.
- Child/renderer fatal-error handling is implemented but fault-injection UI coverage is
  incomplete. API interrupted recovery and normal process shutdown were tested.
- A Starlette TestClient httpx deprecation warning remains. It does not fail the tests;
  changing test HTTP libraries is deferred rather than changing the validated runtime.
- Dependency locks were resolved and clean-installed on Python 3.12 Linux. Windows
  colorama is explicitly pinned, but Windows clean installation is not verified.
- Session active/paused means shell state only. **No microphone/Meet audio is captured.**
  Duration is wall time including pauses. No raw audio or screenshots are written.
- No RAG/citations, ASR/diarization, AI answers, vision, scheduler, installer or model
  onboarding is implemented before its milestone. No GPU benchmark claim is made.
- M0 RTX 4080/Windows hardware feasibility remains blocked as recorded in its report;
  M1 shell validation does not resolve those risks. 8B remains the primary candidate.
- No guaranteed invisibility across Meet share modes. Content protection is defense in
  depth only. Use tab-only sharing and verify with a consenting remote observer.

## 5. Acceptance criteria

| M1 criterion | Status |
|---|---|
| Application actually starts with owned local service and production assets | PASS on Linux |
| Create/rename/select/delete projects with persistence | PASS |
| Dashboard/mini/browser share application state | PASS |
| Start/pause/resume/stop with consent and project guards | PASS |
| Normal quit stops session and releases service port | PASS |
| Interrupted session becomes visibly interrupted on restart | PASS (API integration) |
| Configurable global shortcut; conflict preserves old binding | PASS on Linux |
| Native hotkey invokes companion callback | PASS on Linux X11 |
| Renderer isolation and local API access guards | PASS for executed checks; full audit deferred M7 |
| Collapsible/dismissible always-on-top companion | Implemented; collapse/expand/dismiss/reopen tested, physical foreground behavior manual |
| Tray actions and physical two-monitor usability | Implemented; manual native acceptance pending |
| Windows 11 laptop native acceptance | **UNRUN**, not passed |
| RTX 4080 GPU/continuous transcription feasibility | **UNVERIFIED**, outside M1 shell validation |

## 6. Manual test instructions

Use the repository-root installation commands in README.md. They install dependencies,
build production assets, then run `npm start`; no Ollama or GPU dependency is needed
for this shell milestone. On Windows use a dedicated non-production data profile:

```powershell
$env:PM_COPILOT_DATA_DIR = "$PWD\.m1-data"
npm start
```

1. Create Alpha and Beta, select Alpha, rename it, restart the app and confirm both
   names and selection persist. Delete Beta with confirmation and verify Alpha survives.
2. Start an Alpha session. Confirm Start is blocked until both acknowledgements are
   checked. Confirm the interface explicitly says audio capture is unavailable in M1.
3. Open the companion and **Desktop settings → Open in browser**. Pause/resume from
   different views; verify immediate synchronization and duration. Attempt to switch
   projects/delete the active project and confirm it is blocked.
4. Press Ctrl+Shift+Space while another application is focused. Confirm the companion
   appears and says AI assistance is not yet available. Change the shortcut, test the
   new binding, and try a key held by another application to verify conflict reporting.
5. Drag the companion onto monitor two, collapse/expand/dismiss it, then reopen via
   shortcut and tray. Disconnect that monitor and verify the companion is reachable.
   Restart to test remembered position. Record actual OS/display results.
6. Close the dashboard; confirm the tray keeps the app reachable. Use its Open,
   Show companion, Stop session and Quit commands. Quit during a live session; relaunch
   and verify the history says stopped. In a separate disposable profile force-stop
   the process and verify the next startup records interrupted.
7. Stop the app; verify the browser loses connection and disables mutation controls.
   Restart and reopen the browser from the desktop app to obtain new authentication.
8. In a private consented Meet test, use tab-only sharing and a remote observer. Do
   not infer Windows content-protection behavior from this Linux test run.

For Linux reproduction use a valid X display. This task used an already available
Xorg dummy driver and `DISPLAY=:99 PM_CHROMIUM_PATH=/usr/bin/chromium
PM_TEST_X11_INPUT=1 npm run test:e2e`. XTest is a Linux test fixture only. For Windows,
`npx playwright install chromium` then `npm run test:e2e` runs the portable desktop
flows; the Windows OS hotkey/monitor/tray procedure above remains a manual requirement.
