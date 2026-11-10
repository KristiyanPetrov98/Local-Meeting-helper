# Target laptop benchmark runbook

All Windows commands below are **unrun on target**. Do not interpret these as measured
results. Obtain consent from every participant before capture; use a private test Meet.
Use the existing checkout; a task environment is already isolated, no worktree needed.

## Prerequisites

Windows 11 x64, NVIDIA driver, Python 3.11/3.12 x64, Ollama installed locally.
Record actual GPU name/UUID, VRAM, driver and supported power limit using inventory.
Record AC/battery, power profile, Chrome/Meet version, monitors, GPU selection, ambient
conditions, and idle/display VRAM. N/A power reporting is a limitation, not a zero value.
Install compatible CUDA/cuDNN per the installed CTranslate2 release requirements.
No CUDA runtime was installed or validated in this Linux task.

From repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r scripts/requirements-windows.txt
.\.venv\Scripts\python -m pip check
.\.venv\Scripts\python -m unittest discover -s tests -v
$env:OLLAMA_NUM_PARALLEL = '1'
# Quit any existing Ollama tray/server first so the setting affects its process.
ollama serve
```

Run the server in its own terminal. Install models once with Internet access, then use
local inference offline. Do not disable TLS or signature validation to obtain models.
Model tag availability, licenses, hashes and package compatibility remain unverified.
Record actual Ollama model digest (harness records /api/tags) before comparisons.

```powershell
ollama pull qwen3-vl:8b-instruct-q4_K_M
# Explicit one-time ASR download, outside capture and active meetings:
.\.venv\Scripts\python -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"
.\.venv\Scripts\python scripts/benchmark.py inventory --output results/hardware.json
.\.venv\Scripts\python scripts/capture_probe.py devices --output results/devices.json
```

If the exact tag is unavailable, record the blocker; do not silently substitute another
model or quantization. ASR benchmark uses local_files_only=True, preventing downloads
mid-session. Package pins are direct pins only: generate/review a full Windows lock
with hashes and test clean installation before claiming reproducibility.

## Matrix and procedure

1. Keep normal two-monitor/Chrome/Meet display load. Record idle GPU samples before
   loading models; ensure no unrelated inference sessions or embedding residency.
2. Run 8B alone at 4096. Each run separates first request (warmup) from subsequent
   requests; use at least 10 measured requests, repeat three times for variance.
3. Run Whisper Medium alone on CUDA int8_float16, then CPU int8. Select the verified
   loopback device explicitly. Use separate EN and BG sessions and human reference
   scripts; assess omissions, duplicates and word errors without persisting media.
4. Run each Whisper mode concurrently with 8B at 4096. Run WGC probe alongside it.
   Use live, consented, continuous speech with varied utterance lengths and silence.
5. Advance to 6144 then 8192 only if sampled free VRAM remains >=2048 MiB and no drops,
   overflows, OOMs or growing backlog occur. Record actual prompt_eval_count. Changing
   num_ctx with a short prompt is only allocation testing, not occupied-context testing.
   Increase --prompt-repetitions and inspect prompt_eval_count to exercise near-full
   context with room for output. Synthetic repeated text is not a model quality test.
6. Repeat with --image pointing to a locally made synthetic chart fixture; the fixture
   is supplied transiently and never copied into artifacts. Text-only runs do not
   validate vision latency, visual quality or vision memory use.
7. Run best candidates 5400 seconds under representative meeting load. Monitor device
   changes, backlog and thermals. Run an external capture integrity probe alongside;
   benchmark ASR chunks are five seconds, with a four-chunk queue. Overflow fails.

Examples (replace 12 with the actual selected WASAPI loopback input index):

```powershell
.\.venv\Scripts\python scripts/benchmark.py run --seconds 300 --output results/8b-4096.json
.\.venv\Scripts\python scripts/benchmark.py run --asr cuda --consent --asr-only --audio-device 12 --language bg --seconds 300 --output results/asr-cuda-bg.json
.\.venv\Scripts\python scripts/benchmark.py run --asr cpu --consent --asr-only --audio-device 12 --language en --seconds 300 --output results/asr-cpu-en.json
.\.venv\Scripts\python scripts/benchmark.py run --asr cuda --consent --audio-device 12 --seconds 5400 --output results/concurrent-cuda.json
.\.venv\Scripts\python scripts/benchmark.py run --asr cpu --consent --audio-device 12 --seconds 5400 --output results/concurrent-cpu.json
.\.venv\Scripts\python scripts/benchmark.py run --context 6144 --prompt-repetitions 250 --asr cpu --consent --audio-device 12 --output results/context-6144.json
```

The probe measures end-to-end generation, first token latency, Ollama load/evaluation
counts/timings, sampled GPU memory/utilization/temperature/power and ASR processing
and chunk-end-to-completion lag. Five-second batching adds up to five seconds to a
sample's end-to-end lag; chunk-end lag alone does not prove median user-perceived lag
under five seconds. Production chunking remains a design decision. CPU threads default
to 8; tune based on measured hardware, not an assumed 20 cores.

Aggregate GPU memory samples include desktop/Chrome and other GPU processes; they are
not exact peak allocation or per-model VRAM. Half-second sampling can miss spikes.
Compare baseline, solo, concurrent and /api/ps residency. Never sum unrelated samples
as proof of simultaneous residency. Multi-GPU samples are separate rows; confirm the
4080 is the inference device and review its row, not a desktop GPU's numbers.

## Acceptance and interpretation

Require >=2 GiB observed reserve, no capture drops or ASR errors, stable backlog, no
OOM/crash, complete 90-minute run and acceptable English/Bulgarian quality. Target
median transcription lag <5s measured from live utterance timing; answer completion
<45s target, <=60s initial ceiling. Report cold/warm, p50/p95/max and sample counts.
Errors must remain errors; missing measurements are null, not zero or passes.
`measured_requires_review` is deliberately not a qualification pass. Every report
requires human review and capture/quality evidence. The Python live callback/probe
itself is unvalidated on Windows; callback overhead, resampling, PyAudio thread
behavior and shutdown require target tests. It is not the eventual C# helper.

Model speed, WER, laptop thermals, background memory growth, microphone echo handling,
process loopback, sharing exclusion and installer operation cannot be inferred from
portable unit tests. Final configuration remains undecided until these runs exist.
