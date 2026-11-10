# M3 — live meeting pipeline implementation and target test guide

Date: 2026-11-06. M3 code is implemented and portable checks pass. **Live Windows/Meet,
Whisper Medium accuracy/latency, Community-1 output, and RTX 4080 qualification remain
unverified.** M2 was deliberately left pending at the user's request; M4–M7 were not
started. This is a developer build, not an installer or a qualified meeting recorder.

## Implemented features and changed components

- C# WASAPI microphone + selected-output loopback helper, endpoint enumeration, mono
  resampling, packet sequencing, bounded queues, partial-packet flush, parent-EOF stop,
  disconnect and default-device recovery.
- Separate local faster-whisper worker supporting auto/English/Bulgarian, Medium CPU
  int8 and CUDA int8_float16 profiles, VAD, overlap/word-timestamp deduplication, CPU
  recovery after inference failure, visible backlog/error counters.
- CPU Community-1 adapter with bounded lower-priority refinement, overlapping-window
  provisional labels and manual rename/merge controls. Full model loading is unrun.
- Project/session-scoped text transcripts, pagination, persistence, aliases, manual
  correction preservation, default 30-day configurable retention and project deletion.
- Dashboard audio/device/routing settings, explicit capture checkbox at session start,
  live status, transcript review/history, Retry capture and device changes while paused.
- Safe Electron-crash shutdown, preserving all M1 project/session/hotkey workflows.

Key files: services/capture-windows/{Program.cs,PmCopilot.Capture.csproj,packages.lock.json};
services/api/pm_copilot/{audio,meeting,media_worker,transcript_store,store,app,__main__}.py;
apps/web/src/MeetingPanel.tsx plus client/main/styles; apps/desktop/src/main.ts;
packages/contracts generated schema/types; scripts/{setup-m3.ps1,download-whisper.py};
Python ASR/Windows diarization locks; tests/api, tests/capture-dotnet and tests/e2e;
global.json, CI workflow, this report and m3-architecture.md.

## Checks actually executed

Final automated totals: **24 API/pipeline tests, 3 .NET tests, 5 Electron tests,
4 Vitest tests, and 5 preserved M0 tests passed: 41 total, zero failures/skips on Linux.**
See m3-validation.json for machine-readable status. Native build/publish and conversion tests ran
on Linux with .NET SDK 8.0.427; the Windows executable was cross-compiled, not run on
Windows. Electron ran against Xorg :99 with actual sandboxed renderers and X11 hotkey
input. API/process tests use explicit synthetic/text fixtures, **not real speech**.

- API tests cover M1 regression, transcript isolation/persistence/pagination/retention,
  speaker correction/merges/cascades, bounded queues, discontinuities, overlap, CPU
  failure recovery and interprocess capture-reader independence from a slow fixture.
- Native tests exercise downmixing, resampling and default-device notification logic.
- Electron tests exercise shared dashboard/browser/companion, CRUD/hotkeys/restart,
  normal quit, actual main-process crash and API shutdown, plus text-fixture transcript
  review/rename/merge/persistence/project isolation. Fixtures never validate ASR quality.
- ASR hash-lock installation and pip check passed; faster-whisper 1.2.1 and CTranslate2
  4.8.5 imported. Bundled Silero VAD ran on one second of silence and returned no speech.
  CPU runtime reports float32, int8 and int8_float32 support. This is not a Whisper test.
- Actual worker with a missing local model failed closed with worker_start_HFValidationError
  and exit 2. No automatic cloud fallback or model download was attempted by the worker.
- The helper's Linux preflight returned windows_required and exit 2.
- Hugging Face model-host access failed at the environment proxy: CONNECT 403. No
  Whisper/Community-1 weights were available, so real-model inference could not run.
- Python compilation, TypeScript checking, contract generation and production web /
  Electron builds passed. Remote GitHub Actions workflows were saved, not executed.

## Windows setup (PowerShell, repository root)

These target-machine commands are **not claimed as executed on Windows**.
Prerequisites: Windows 11 x64, Node 24, Python 3.12 x64, .NET SDK **8.0.427** (global.json)
and .NET 8 runtime. Reassess the .NET support version at packaging time. For CPU Medium,
no CUDA runtime is needed. Install matching CTranslate2 CUDA/cuDNN prerequisites before
selecting GPU mode; driver/CUDA compatibility is not verified here.

```powershell
.\scripts\setup-m3.ps1
.\.venv\Scripts\python scripts/download-whisper.py --model medium
$env:PM_WHISPER_MODEL = "$PWD\models\runtime\whisper-medium"
$env:PM_COPILOT_DATA_DIR = "$PWD\.m1-data"
npm start
```

The explicit one-time model downloader contacts Hugging Face, pins the resolved source
revision and records local SHA-256 digests in installation.json. Review the model license
and artifact identity. Installation needs network access; meeting-time model inference
is local-only. Never disable TLS/checksum checks to work around download failures.
Keep the whole capture helper publish directory together. The API finds it automatically;
PM_CAPTURE_HELPER can override the executable's trusted host path. No secrets belong in
these environment variables, chat, logs or saved scripts.

Optional Community-1 setup requires accepting its upstream license/access conditions
and obtaining a complete offline snapshot through Hugging Face's supported authenticated
local tooling. Authenticate securely on your laptop; do not send a token in chat.

```powershell
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-diarization-windows.lock
.\.venv\Scripts\python -m pip check
# After accepting the model conditions and authenticating with the local HF CLI:
.\.venv\Scripts\hf download pyannote/speaker-diarization-community-1 --local-dir models/runtime/community-1
$env:PM_DIARIZATION_MODEL = "$PWD\models\runtime\community-1"
```

Check optional imports before enabling refinement:

```powershell
.\.venv\Scripts\python -c "from pyannote.audio import Pipeline; import torch; print(torch.__version__)"
```

Restart the application after installing model/runtime assets. Enable Community-1 in
Audio & transcript, save settings, then explicitly enable capture when starting a
session. The Windows-specific diarization lock was resolved and hash-pinned, but its
full installation and model compatibility were not executed here. It pins Torch 2.8,
Torchaudio 2.8 and TorchCodec 0.7; FFmpeg/runtime DLL requirements must be checked on the
laptop. Diarization always selects CPU, even if the Torch wheel supports CUDA. Without
these assets, keep refinement disabled and regard playback speakers as unrefined.

## Manual functional and acceptance test

1. **Route audio:** connect headphones; open a private Meet with consenting participants.
   In Meet audio settings choose the intended mic and playback output. In PM Copilot,
   refresh devices and choose those same endpoints. Save CPU / Medium / auto-language
   settings. Output loopback includes unrelated apps; pause other playback.
2. **Start explicitly:** create/select a project, click Start session, acknowledge
   participant consent and tab-only sharing, then enable local audio capture. Verify
   starting changes to capturing and packet count increases. An active shell session
   without that checkbox is not listening. Errors must remain visible; no fake text.
3. **Exercise both sources:** alternate local/remote English and Bulgarian speech,
   silence, short/long utterances and overlap. Verify text, timestamps, source/language
   labels and no hallucinations on silence. Compare actual utterance-to-text latency
   and omissions against your live reference; no accuracy claim exists yet.
4. **Speakers:** with Community-1 assets, use two remote speakers for over 30 seconds;
   observe refinement. Rename/merge, continue speaking and check corrections persist.
   Long absence/reappearance may create a new provisional ID requiring a manual merge.
5. **Pause/recovery:** pause and confirm capture stops. Change an endpoint while paused,
   save and resume. Disconnect/reconnect, switch the Windows default output, and verify
   visible reconnect/error state and eventual recovery. Specific-ID selection never
   silently changes devices. After exhausted recovery use Retry capture or pause to
   select a replacement. Missing audio during outages cannot be recovered.
6. **Stop/history:** stop, allow finalization (up to 30 seconds), restart the app and
   review the transcript. Change projects; confirm text and speaker edits never cross
   scope. Delete a disposable project and verify its transcript disappears. Test
   retention on a disposable profile; existing transcript deletion is irreversible.
7. **Speakers route:** repeat using external speakers and the speakers routing profile.
   Check echo and duplicate suppression with simultaneous talk. This is a text heuristic,
   not acoustic echo cancellation; do not approve this route without actual validation.
8. **Resource test:** repeat the M0 8B/Whisper CPU-vs-GPU matrix on the RTX 4080, monitoring
   queue depth, dropped chunks/packets, ASR errors, VRAM, latency and thermals. A 90-minute
   run must have no lost speech/OOM/unbounded growth before accepting the profile. No
   continuous-under-8B result has been measured by this task.
9. **Privacy/lifetime:** verify no WAV/media files are created, then test normal quit
   and a forced Electron exit in a disposable profile. Audio must stop and the API close.
   Use tab-only sharing and a consenting remote preview observer; broader-mode content
   protection and Windows capture exclusion remain unverified.

## Acceptance status and remaining limitations

| Criterion | Status |
|---|---|
| Native helper compiles / Windows x64 publish exists | PASS (cross-build) |
| Pure conversion/default-notification tests | PASS |
| Portable pipeline/queue/transcript/scope/retention tests | PASS |
| Desktop startup, M1 regression, transcript UI and crash recovery | PASS on Linux |
| Actual microphone / Meet / headphones / speakers / device recovery | UNRUN on Windows |
| Actual English/Bulgarian Whisper Medium recognition and latency | BLOCKED by unavailable weights / target audio |
| Actual Community-1 output and full dependency installation | UNRUN |
| Stable speaker identity across long absences | LIMITATION: manual merges can be needed |
| Process/tab-specific Meet capture | NOT IMPLEMENTED; selected-output fallback is explicit |
| Acoustic echo cancellation | NOT IMPLEMENTED; conservative text/time dedupe only |
| 8B concurrent transcription / laptop VRAM / 90-minute stability | UNRUN |
| Installer / clean-machine non-developer experience | M6, not implemented |

No actual ASR latency, WER, diarization quality, VRAM or continuous meeting measurements
are fabricated. Four-second windows add batching latency; physical device clocks and
word overlap need target tests. Overload/failed recovery can lose chunks with visible
counts. Finalization has a deadline and warns when incomplete. The UI lists the latest
20 sessions and pages 200 transcript segments at a time (view cap 1,000). All retained
text remains in SQLite; session metadata and speaker names are not removed by text
retention. None of the unrun hardware checks is a release pass.

## Reproduce automated checks

```powershell
.\.venv\Scripts\python -m pip install --require-hashes -r services/api/requirements-dev.lock
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m pytest tests/api -q
npm test
npm run typecheck
npm run build
dotnet test tests/capture-dotnet -c Release
npx playwright install chromium
npm run test:e2e
```

Portable API tests explicitly disable hardware capture. The POSIX subprocess fixture
is skipped on Windows; it passed on this Linux run. Native conversion tests and text
fixtures do not verify a physical microphone or speech model. Run the consented manual
procedure separately. Codegen uses an activated API virtual environment with
`npm run contracts`. The Windows build script is additive and keeps M0/M1 files/data.
