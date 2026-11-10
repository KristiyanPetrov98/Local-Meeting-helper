# M7 release qualification on Windows 11 / RTX 4080 Laptop

Current decision: **blocked**. Portable cloud tests are not a Windows/RTX 4080 qualification. No Windows installer has been built or published by this cloud run.

## Build and preserve evidence

1. Use this source on a Windows x64 build machine with Node 24, Python 3.12 and **.NET SDK 10.0.403**. Run `scripts/package-windows.ps1`, or dispatch the manual Windows installer workflow. Preserve `release/*Setup.exe`, `release/SHA256SUMS.txt` and `build/notices`, especially `runtime-manifest.json`, `backend-smoke.json` and `windows-build.json`. The script requires the full model runtime and actual bundled imports; a Linux backend cannot masquerade as a Windows installer. Building/dispatching has not been done here.
2. Run the available Python, .NET, Vitest, type and Electron checks on Windows as well. The cloud portable report applies to its source, not proof that every platform-specific branch ran.
3. Install the resulting per-user candidate on a clean Windows 11 machine without developer Python/Node/.NET SDK on PATH. Start it, ingest a real harmless document, search/open its citation, create a session, restart and confirm history. Test uninstall/reinstall and expected data preservation. Current packaging is unsigned; record Windows warnings and your distribution/signing decision. Do not call unsigned packaging a signed release.
4. Record the exact installer SHA-256, source digest, GPU/driver, OS, Ollama version, model digest, capture devices and configuration in private operator evidence. The metrics export omits sensitive project/device names. Keep the unredacted machine records locally if needed.

## Models and short checks

Start with **Qwen3-VL 8B Q4_K_M**, context **4,096**, and **Whisper Medium CPU int8**, with CPU Community-1 diarization. Use the existing local embedding model and CPU embeddings. Keep the 2,048 MiB GPU reserve and estimated 8,192 MiB generation budget initially. These are candidates, not measured recommendations for this physical laptop.

Use the setup wizard to install/import approved weights, acknowledge required upstream access/licenses, configure hardware and run actual offline self-tests. The new Windows diarization dependency set must pass real imports and inference before release. Run M6's short live benchmark with both English/Bulgarian speakers; review transcript and model quality. Apply a profile only after that review. Try CUDA Whisper only if the real concurrency test preserves transcription and fits measured memory. Prefer CPU placement before reducing the primary 8B model. Small/tiny Whisper choices are explicit alternatives requiring their own quality review; no 4B fallback has been validated.

After setup, disconnect external networking while keeping loopback enabled. Repeat model self-tests, project search, transcription and manual assistance. Record failed downloads separately from offline inference. First-time model installation naturally requires network or a trusted local snapshot.

## Actual 90-minute meeting

1. Open a consented Google Meet with another participant/test source. Use the same microphone/output selected in PM Copilot. Test headphones and external speakers separately; inspect echo behavior and source attribution. Rename/merge provisional speakers and verify persistence. A detected language or an audible packet is not an accuracy verdict.
2. Select a project with a harmless document containing known facts. Create another project with conflicting facts as an isolation test. Explicitly declare the intended tab-sharing mode and select a harmless external window. Inspect **Meet's own preview**. Broader/unknown sharing must hide the companion and stop selected-window capture while transcription continues. The app cannot enforce Meet's picker or guarantee OS capture exclusion.
3. Start the consented session with live transcription and the screen/risk options. Open **Set up PM Copilot → 6. Device benchmark → Start qualification recording**. Keep the session active. The recorder produces no prompts or answers; all assistance remains shortcut/button requested.
4. Over at least 90 minutes, maintain both audio sources and use English and Bulgarian. Trigger at least ten actual relevant answers using the global shortcut and at least five no-question examples. Include grounded project questions and inspect every shown source locator. Exercise changing/stable windows, screen-assisted answers, document risks and sharing changes. Never insert fixture transcripts or fake model results into this run.
5. Observe memory for **all processes**, not just the exported backend RSS: Electron, frozen API, ASR/diarization/native helpers and Ollama. Record stable post-warmup working sets, GPU memory, queue behavior, CPU use and any OOM/driver resets. Target median ASR lag <5 s, manual median <45 s and maximum <=60 s, zero dropped media/citation/project/suppression errors, and no sustained memory growth. The recorder exports sampled GPU totals and model residency; independent worker memory/quality review is still required.
6. Wait until at least 90 minutes have been observed with active capture. Stop the **session**, allowing final native counters/transcription to flush, then click **Finish qualification recording** and **Download qualification metrics**. A run with missing native final counters, gaps, failed requests or missing criteria stays failed. Cancel/quit loses the in-memory recording; a crashed or early run cannot qualify.
7. Review output relevance, bilingual accuracy, speaker changes, citations, risk discretion, sharing preview, offline inference and restart behavior. Inspect the application data directory for raw audio/images; documents/transcripts/requested answers are expected persistent content. Do not export meeting content with public test artifacts. OS paging/crash dumps and third-party recording are outside the app's persistence guarantee.

## Release decision command

The cloud artifacts `m7-validation.json` and `m7-dependencies.json` record portable checks and dated advisory scans. A changed source digest requires rerunning them. The Windows build script produces `windows-build.json`; the app produces `pm-copilot-target-qualification.json`.

Create a private operator review JSON with this structure; set a check true only after performing and reviewing it:

```json
{
  "source_digest": "the matching 64-character source digest",
  "installer_sha256": "the actual matching installer SHA-256",
  "reviewer": "operator name",
  "reviewed_at": "ISO timestamp",
  "checks": {
    "clean_windows_install": false,
    "headphones_and_speakers": false,
    "bilingual_accuracy": false,
    "speaker_renaming": false,
    "answer_and_screen_relevance": false,
    "risk_indicators": false,
    "sharing_preview": false,
    "no_raw_media_saved": false,
    "offline_inference": false,
    "restart_persistence": false,
    "worker_memory_bounded": false,
    "licenses_reviewed": false,
    "project_isolation": false,
    "no_question_quality": false
  }
}
```

```powershell
.\.venv\Scripts\python scripts/qualify-release.py `
  --portable docs/m7-validation.json --dependencies docs/m7-dependencies.json `
  --target C:/private/pm-copilot-target-qualification.json `
  --windows build/notices/windows-build.json `
  --installer release/PM-Copilot-0.1.0-x64-Setup.exe `
  --review C:/private/operator-review.json --output C:/private/release-decision.json
```

Exit **2** means blocked, including missing evidence; exit **0** means the supplied matching evidence passed policy. Operator records are attestations and can be edited; this tool is not a tamper-proof audit. Qualification does not sign, upload, publish or send a message. Keep the current cloud decision blocked until the required real-machine work has been done.
