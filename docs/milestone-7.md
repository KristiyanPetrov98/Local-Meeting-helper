# M7 — final integration and release qualification

2026-11-09. **Portable implementation/validation passed; release acceptance is BLOCKED.** Windows installation, live audio/vision, actual local model quality, GPU memory/latency and a 90-minute RTX 4080 Laptop meeting have not been verified. No installer was published and no cloud environment configuration was republished.

## 1. Features implemented

- Sustained integration testing across actual subprocess pipes, project-scoped ingestion/search, source-verified answers, transient screen processing, sharing guards and persistence. Explicit model/capture fixtures are confined to tests.
- HTTP streaming body bounds, credential comparison that safely rejects malformed Unicode, non-reflecting validation errors, no-store denial responses and robust event-channel message rejection.
- Source-version-aware citation cache invalidation, bounded retained memory and indexed source-line offsets. External SQLite source mutation cannot remain hidden by a warm cache.
- A working in-app 90-minute target telemetry recorder with start/stop/export controls, actual GPU/capture/request metrics, bounded samples and failed/missing-check reporting. It never starts generation or marks the release qualified.
- A source-bound release evidence evaluator, Windows installer build evidence and operator qualification procedure. Missing target/installer/review evidence blocks release.
- Supported .NET 10 LTS helpers and dependency advisory remediation, regenerated hashed locks, refreshed runtime notices and dated scans covering Windows-only pins as well as the local environment.

The initial M6 audit confirmed real test, architecture, native helper, frozen backend and packaged Linux outputs existed. Its 244-test report explicitly left Windows/real-model acceptance open. M7 reran and extended validation; file presence was not treated as a test pass.

## 2. Files and components changed

| Area | Files |
|---|---|
| API security | `services/api/pm_copilot/security.py`, `app.py`, `setup_api.py` |
| Citation integrity/cache | `services/api/pm_copilot/document_store.py` |
| Target telemetry and evidence policy | `qualification.py`, `build_identity.py`, `release_policy.py` in the API package; `scripts/qualify-release.py` |
| Dashboard | `apps/web/src/QualificationPanel.tsx`, `SetupPanel.tsx` |
| Tests | `tests/api/test_m7_security.py`, `test_m7_integration.py`, `test_m7_qualification.py`, `test_m7_release.py`; existing bulk-fixture seeding in `test_assistance.py`; `tests/e2e/m7.spec.ts` |
| Dependencies/native builds | `package.json`, `package-lock.json`, Python document/dev/diarization inputs and affected locks; `global.json`; all three C# project/lock pairs; helper default paths in `meeting.py` and `screen_native.py` |
| Packaging | `packaging/backend.spec`, `scripts/collect-notices.py`, `scripts/package-windows.ps1`, native/installer workflows, .NET runtime licenses/notices |
| Measurements/docs/contracts | advisory audit/benchmark scripts, updated generated API contracts, helper READMEs, top-level README, M7 architecture/procedure/reports |

Source identity: `cc68fe7388646c48ec7d42d9fc38a759bf73d450ae1a168d32c5062c64f2aaa7`. The frozen backend and notice manifest carry the same digest. Reports/docs are excluded from that hash.

## 3. Tests executed and measured results

| Check | Executed result |
|---|---|
| Full Python API suite | **248 passed**, 102.65 s; includes **34 M7 cases** |
| Electron source application | **12 passed** in the final combined suite; real tray/window/session/project/document/sharing/onboarding workflows, global shortcut through X11 and new recorder availability controls |
| Packaged Linux Electron app | **1 passed** in the final combined suite; actual installed-layout binary, outside checkout, no Python/Node on PATH; bundled parsing/import and valid citation workflow |
| Vitest | **10 passed** |
| M0 Python unit tests | **5 passed** |
| Native .NET conversion tests | **3 passed** under .NET 10 on Linux |
| Total | **279 passed**, zero final failed/skipped cases in the executed suites |
| Type checks / production web+desktop build | Passed |
| OpenAPI/TypeScript regeneration | Passed |
| Python byte compilation / `pip check` | Passed |
| Locked NuGet restores / self-contained win-x64 helper cross-publishes | Passed; Windows execution unrun |
| Clean PyInstaller build / actual frozen backend smoke | Passed; parser subprocess, local RAG/citations, missing-model blocking and parent-EOF shutdown exercised |
| Linux desktop packaging | Passed after the build-dependency override |
| npm / Python / NuGet advisory scans | No reported advisories after remediation; see dated machine-readable reports and their feed scope |
| Windows packaging attempt here | Correctly refused Linux backend at the existing full-Windows-runtime guard, exit 1; **no Windows Setup.exe** |
| Hardware inference / capture probes | Exit 2: `blocked_no_nvidia_smi` / `blocked_requires_windows` |

The API JUnit report is [m7-api-tests.xml](m7-api-tests.xml); Electron output is [m7-electron-tests.txt](m7-electron-tests.txt). Commands and portable scope are in [m7-validation.json](m7-validation.json). The final combined Electron suite ran **13 tests in 46.3 seconds**, with the packaged application supplied; no package test was skipped or counted twice.

### Sustained portable workload

[m7-portable-soak.json](m7-portable-soak.json) records **60.68 seconds** of actual interprocess/application activity with explicitly synthetic media/model fixtures:

- **1,192 audio packets**, 32 transcript segments, **46** requested generated responses.
- **Zero** observed packet gaps, dropped chunks, ASR errors or reconnects; maximum audio queue depth **1** (bound 8).
- Each measured generation interval continued receiving capture packets. Selected-window PNG decoding/background observation, broader-sharing stop, source citations and cross-project rejection were exercised together.
- Backend RSS grew from **268.97 to 270.59 MiB**, maximum **270.59 MiB**. This is the backend process only, in a shared test host; it excludes model/native workers and is not a long-run growth guarantee.
- Median fixture request completion **180.40 ms**. This is plumbing latency with deliberately small model fixtures, **not Qwen3-VL latency**.
- Raw PCM and its base64, PNG and its base64, and API-token canaries were absent from application data after shutdown. Persistent transcript/history recovery and isolation were checked after reopening the actual database. This is a targeted regression check, not proof about OS paging/crash dumps or third-party software.

### Citation cost

Two actual parser/store runs used 1.95 million synthetic text characters and 500 warm citation lookups of the last ten chunks. Before/after raw data is in `m7-citations-before.json` and `m7-citations-after.json`.

| Measurement | Before | Final implementation |
|---|---:|---:|
| Cold lookup | 20.21 ms | 39.11 ms |
| Warm median | 0.635 ms | 0.712 ms |
| Warm p95 | 2.984 ms | 2.014 ms |
| Warm maximum | 7.813 ms | 11.770 ms |
| Warm traced peak allocation | 51,877 bytes | 51,546 bytes |

Cold parsing now also builds newline indexes and accounts retained objects. Shared-host noise and these small differences do **not** establish a general speed improvement; median/cold results regressed in this run. The useful verified gains are source-change detection, bounded retention and removal of repeated prefix scanning. GPU/model performance remains unmeasured.

## 4. Remaining bugs, limitations and blockers

- This host is Linux with no NVIDIA GPU or local model service/weights. Actual Qwen/Whisper GPU memory, model latency, bilingual accuracy and 90-minute concurrency results are **unmeasured**, not zero or passed.
- Real Windows installer/build/import/upgrade/uninstall, WASAPI/Meet audio and WGC selected-window capture remain unrun. Both native helpers cross-build; that does not verify hardware APIs. The screen helper emits one nonfatal CS9191 `ref`/`in` recommendation.
- The updated Windows diarization stack resolves and has a clean advisory scan, but runtime imports, bundled native dependencies and inference need Windows testing. The full Windows smoke/build must fail if those imports fail.
- No validated fallback model/profile exists. Recommended starting candidates remain Qwen3-VL 8B Q4_K_M / 4,096 context, CPU int8 Whisper Medium and CPU diarization, with 2 GiB VRAM reserve. CUDA Whisper, smaller Whisper options and resource-budget changes need independent measurements and quality review.
- The 90-minute recorder and policy have fixture-based failure-path tests. **No real target recording or successful target-hardware UI/export run has been performed here.** Backend RSS is not combined process memory; content relevance, transcript accuracy and complete memory review remain manual gates.
- The companion/sharing protection follows a declared mode and fails closed when unavailable. It cannot control Meet's picker or prove exclusion from every OS capture path. Human preview review is mandatory.
- Local SQLite content is plaintext under the OS account. Citations prove quote/locator identity and scope, not that every generated interpretation follows the evidence. Installer signing and an independent security/license audit are not supplied by these tests.

The initial package issues were addressed: vulnerable pypdf/pytest/Torch/minimatch pins and near-end-of-support .NET 8. The final audit also fixed platform-dependent source-hash ordering and a cross-thread SQLite writer in an existing bulk test fixture. The fixture now seeds on the API event loop, matching the application write path. Earlier failed runs are not counted as validation; no unresolved portable test failure remains after the final complete run.

## 5. Acceptance criteria

| Spec §15 criterion | Current evidence / acceptance |
|---|---|
| 1. Detect RTX 4080 Laptop | **Blocked**: no target hardware |
| 2. 8B fits memory / validated fallback | **Blocked**: actual VRAM/model run absent |
| 3. Continuous Whisper during 8B generation | Portable isolation test **passed**; real concurrent inference **blocked** |
| 4. 90 minutes without OOM | Recorder/policy failure cases **passed**; actual meeting **blocked** |
| 5. Headphones and external speakers | **Blocked**: Windows/live sources absent |
| 6. English/Bulgarian transcription | Bilingual pipeline fixtures **passed**; model accuracy **blocked** |
| 7. Editable speaker IDs | Existing automated API/UI checks **passed**; target diarization review pending |
| 8. Relevant global-shortcut answers | Shortcut/orchestration checks **passed**; real-model relevance **blocked** |
| 9. No-question suppression | Automated examples and generation-call suppression **passed**; real transcript review pending |
| 10. Scoped project retrieval | Actual parser/SQLite/FTS integration and isolation **passed** |
| 11. Genuine resolvable citations | Stored-source/hash/locator/cache-mutation and packaged workflow tests **passed** |
| 12. Relevant screen context | PNG/change/admission/orchestration checks **passed**; WGC/model quality **blocked** |
| 13. Discreet risk indicators | Automated UI/state/expiry checks **passed**; real risks/Meet presentation pending |
| 14. No raw media persistence | Targeted portable canary tests **passed**; target data/OS review pending |
| 15. Sharing safeguards | Declared-mode automatic checks **passed**; actual Meet preview/exclusion **unverified** |
| 16. History after restart | Source restart/persistence and packaged storage workflows **passed** |
| 17. Offline AI | Fixed-loopback clients and portable core checks **passed**; actual disconnected model inference **blocked** |
| 18. Clean-machine Windows installer | **Blocked**: no Windows build/install evidence |

**M7 release acceptance: BLOCKED.** `m7-release-decision.json` must retain `release_ready: false` while any mandatory real-machine gate lacks evidence. Finishing the implementation stage is not qualification of the laptop or a release.

## 6. Manual testing and reproduction

For local development, install the documented locked dependencies, activate `.venv`, run `npm run contracts`, `npm run typecheck`, `npm test`, `npm run build`, the Python suites and native tests, then `npm start`. On Linux, Electron needs an X display; the test report records the cloud display/browser settings. To reproduce the mixed-workload test for 60 seconds:

```bash
PM_M7_SOAK_SECONDS=60 PM_M7_SOAK_OUTPUT=docs/m7-portable-soak.json \
  .venv/bin/python -m pytest tests/api/test_m7_integration.py -q
```

On Windows, follow [release-qualification.md](release-qualification.md) for the actual installer, offline models, audio/Meet/window checks, 90-minute recorder/export and operator review. The setup wizard's **Device benchmark** page contains both the existing short check and the separate long-run controls. Stop the session before finishing the long recording.

To reproduce the current blocked release decision without pretending target evidence exists:

```bash
.venv/bin/python scripts/qualify-release.py \
  --portable docs/m7-validation.json --dependencies docs/m7-dependencies.json \
  --output docs/m7-release-decision.json
```

Expected exit: **2**. Portable/dependency gates pass; target measurements, Windows installer and operator-review gates remain blocked. Do not publish based only on the portable test count.
