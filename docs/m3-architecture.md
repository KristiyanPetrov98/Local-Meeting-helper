# M3 implementation decisions

M3 was explicitly requested before M2. M1 stays intact; RAG, documents, answers, vision
and packaging remain out of scope. No model configuration for Qwen3-VL 8B was changed.

## Process and media boundaries

Electron owns FastAPI through an inherited control pipe. Keeping that pipe open lets
the API detect parent death, close its loopback listener and tear down capture. The
API owns a C# WASAPI helper and separate ASR/diarization Python processes. Helper stdin
EOF also stops capture if the API is killed. Private inherited pipes replace the M0
proposed named pipe for this iteration: no extra listener, discovery token or pipe ACL
is needed. Commands and media are inaccessible to browser APIs except through the
existing authenticated service; no public PCM ingestion/fake-transcript endpoint.

NAudio captures the selected microphone and render output independently, downmixes and
resamples to float32 mono 16kHz in RAM. Packets are approximately 100ms with source,
sequence, common elapsed timestamp and sample count. The native output channel holds
at most 128 packets; its drop count is reported. The parent validates sizes, rate,
source, timestamps and finite amplitudes; sequence/time discontinuities clear partial
chunks and increment visible diagnostics. Loopback silence may produce no packets and
can also appear as a timestamp discontinuity; that is not proof of lost speech.

The API assembles four-second ASR windows with half-second overlap and an eight-window
queue. Word timestamps remove already-accepted overlap. Capture is a separate async
reader and keeps running while model subprocesses work. Overflow drops a whole window
and displays a persistent warning/count; this is bounded failure handling, not an
acceptance pass for continuous transcription. Python orchestration does only bounded
signal work; all actual inference is outside its event loop. GPU inference failures
attempt CPU ASR recovery and keep capture active; failed chunks are counted. Repeated
model failures require explicit Retry capture and may lose speech to bounded overflow.

Whisper Medium starts on CPU int8 by default, preserving generation-model VRAM. CUDA
int8_float16 is selectable for actual laptop benchmarking. Neither profile is qualified
for continuous laptop use. Workers use local model directories, local_files_only and
HF_HUB_OFFLINE. ONNX telemetry is disabled through its API and pyannote/HF telemetry
through their configuration. Optional model installation is a separate explicit command.

## Speakers and audio routing

Community-1 loads from a complete local snapshot on CPU in a lower-priority process
(two torch threads and Windows BELOW_NORMAL_PRIORITY_CLASS). Thirty-second remote
windows retain ten seconds of overlap; one refinement job waits, and jobs are deferred
when ASR queue depth exceeds one. Turn-overlap alignment gives stable provisional IDs
when consecutive windows share a speaker. It does not perform reliable identity
recognition across long absences; new labels can need manual merging. No human names
are invented. The microphone label is You; unrefined playback is explicitly labelled
Remote (unrefined). Refined remote labels are Speaker 1, Speaker 2, etc.

Rename and merge are session scoped, aliases survive future segments, and manually
corrected speakers are not overwritten by background refinement. Without local
Community-1 assets, the user can run ASR with source-level labels while setup is pending;
this is an explicit unrefined mode, not a diarization success claim.

For speakers, a conservative text/time-overlap deduper prefers playback over a matching
microphone segment. It is not acoustic echo cancellation and can suppress intentional
near-simultaneous repetition. Headphones are the first test route. Meet integration is
selected output routing, not a browser extension or process/tab isolation; all other
applications on the chosen output are included. Process loopback remains unavailable.

## Lifecycle and recovery

Capture is opt-in per consented session; ordinary M1 shell sessions still work on Linux
or without models. Starting returns state=starting while local models initialize; only
a native started message produces capturing. Initialization failure is visible and does
not claim audio is being captured. Pause/stop signals native stop, drains packets and
waits up to 30 seconds for queued/tail ASR before cancellation. Three-second native-stop
timeout is explicit. Raw buffers are released on pause, stop, retry and fatal shutdown.
Pause permits replacing devices/settings; resume preflights the new configuration.
Session drop/error counters and the provisional-ID allocator survive pause/retry so
restarting capture does not conceal losses or assign an old ID to an unrelated turn.

WASAPI disconnects and default-multimedia-route changes restart the helper with bounded
backoff. Specific endpoint IDs never silently switch to unrelated devices. Five failed
recovery attempts require Retry capture; a healthy period resets retry count. Recovery
cannot reconstruct uncaptured speech. Device/driver behavior is still unverified here.

## Persistence and UI

SQLite migrations add speakers/aliases/manual-correction flags and text-only transcript
segments. Session/project validation precedes every read/edit; scoped deletes cascade.
Segment keys deduplicate retries. Capture/source timestamps, language, text and speaker
ID are stored, never PCM or screenshots. Thirty-day retention is configurable; cleanup
runs at startup, on retention edits and periodically. Session metadata and speaker
names remain until project deletion; text deletion is not a forensic erasure guarantee.

REST exposes device/settings/retention and project/session-scoped transcript/speaker
routes. Versioned snapshot events now include lightweight capture status/counters; text
is paged through the authenticated API (200 segments/page). The browser and desktop
show the same source. The transcript UI caps a view at 1,000 loaded segments and shows
sessions from M1's most recent 20 history entries. Production speaker/ASR results are
never populated from test fixtures.
