# M6 packaging and guided setup architecture

M6 keeps the M1–M5 API, project store, document verifier and isolated media workers.
It adds installed-resource resolution, a fixed worker launcher, setup operations and
measurement-backed configuration. M7 release qualification is not implemented here.

## Installed layout and process ownership

```text
PM Copilot.exe                       Electron shell / embedded Node runtime
resources/app.asar                   bundled main + preload code
resources/web/                       static production React assets
resources/backend/pm-copilot-api/     PyInstaller onedir executable + Python/native libs
resources/helpers/audio/             self-contained Windows x64 WASAPI helper
resources/helpers/screen/            self-contained Windows x64 WGC helper
resources/notices/                   dependency inventory and license texts
userData/copilot.sqlite3             existing data plus setup results/settings
userData/models/<approved-model>/    separately installed speech/diarization snapshots
```

`backendLocation` selects an installed executable when `app.isPackaged` is true. It
ignores the development Python override and supplies real helper paths and the static
web directory. Source launches retain their existing virtual-environment entry point.
The app never writes models or application data into the installed resources tree.

The backend entry point dispatches only four fixed worker roles: document, media,
assets and runtime checks. A frozen worker launches the same executable with a fixed
`--worker` role; source mode uses the existing Python module. Configuration, captured
PCM and credentials travel through private pipes, never shell arguments. Parent EOF
cancels setup and media jobs and terminates their owned children before HTTP drains.
A parser can therefore run in a clean installed app without a source checkout/Python.

## Installer build

The Windows build script creates an isolated build environment from the existing
assistance, ASR, Windows diarization and new build-tool hash locks. It publishes both
native helpers with `--self-contained true`, builds all supported model libraries into
the Python executable, collects notices, smoke-tests the bundle, then invokes the
pinned electron-builder NSIS x64 target with publication disabled.

The installer is an unsigned per-user candidate with selectable installation directory,
no elevation, shortcuts, and app-data preservation on uninstall. No update/publish
service is configured. Models are installed separately; only faster-whisper's small
MIT-licensed Silero VAD runtime asset is retained. Pretrained checkpoint/media fixtures
are filtered from the backend collection. Python, frontend, .NET/NAudio and VAD notices
are included; the inventory does not replace final license/security review.

The before-pack gate requires a real Windows backend inventory, all supported runtime
libraries, x64 PE signatures for the backend/helpers, and self-contained .NET core
files. It rejects Linux binaries instead of producing an unusable Windows installer.
A manual GitHub Actions workflow builds/uploads a candidate on Windows; it has not run
in this chat. Clean-machine install/uninstall, signing, native capture and model/GPU
qualification remain open.

## Setup states and operations

The dashboard has a non-blocking first-run wizard, which remains available after
acknowledgement. Steps cover hardware/dependencies, licenses/assets, consented live
capture, offline runtime tests, a short device benchmark and privacy/sharing limits.
Read-only status/diagnostics never download models or start capture. CPU/RAM/disk,
NVIDIA memory/residency and actual package presence are labelled observations.

Only one setup operation runs at once: download, local import, integrity verification,
offline self-tests or benchmark. There is no setup queue. Installation/tests/config
changes require an idle meeting; session startup is blocked while they run. A benchmark
requires an existing consented capturing session. Manual questions, pause and stop
preempt that benchmark. Early cancellation, parent death and restart leave no successful
qualification record. `setup_runs` stores results/status and synthetic benchmark output;
it does not duplicate live transcript text, PCM, frames, import paths or access tokens.
Interrupted rows recover as interrupted, never passed.

## Approved model installation

The catalog fixes the primary 8B and embedding Ollama tags, multilingual Whisper
Medium/Small/Tiny repositories and Community-1. License/access acknowledgement and a
one-time network acknowledgement are mandatory for download. Ollama pulls use only the
fixed loopback API; already-present exact models avoid another pull. Redirects and
unapproved IDs/URLs are rejected. A successful pull must be followed by exact model
identity/digest resolution; installation alone does not validate inference.

Hub downloads run in a separate setup-only worker, resolve an immutable repository
revision, disable telemetry, and record SHA-256 file hashes. A gated access token is
passed through private stdin only, not saved in reports/settings or printed in logs.
Snapshot installs use bounded staging and atomic promotion. Existing models require
explicit replacement. Reserved partial download/staging names are cleaned on recovery,
and an interrupted replacement's previous model is restored when needed.

Local imports use an OS folder picker. The renderer can request only an approved model
ID and acknowledgement; it cannot supply a filesystem path. The native host adds a
second, private per-launch capability when submitting the selected path to the API.
The browser bearer token alone cannot authorize that route. Snapshot checks reject
symlinks, oversized inventories and executable files; Community-1 must use the approved
pipeline class and included local embedding/segmentation paths. Integrity verification
rechecks the managed manifest and file inventory. Local provenance is user-attested,
not a signed upstream attestation; trusted checkpoints and their access conditions
must still be reviewed. Models are not treated as ordinary untrusted project documents.

## Evidence and profiles

Offline checks actually exercise writable storage, isolated SQLite/FTS/parser/citation
scope, no-question suppression and the child parser. They import model runtimes in an
isolated offline worker, run exact local generation/vector checks, attempt CPU Whisper
load plus synthetic silence and Community-1 load when files exist, and enumerate
native devices/windows when dependencies permit. Missing models/Windows capabilities
are blocked, not passed. Silence inference is not speech-accuracy proof; enumeration
is not capture proof; fixed local clients are not proof of OS-wide network isolation.

The short device benchmark waits for live baseline speech, then executes three neutral
120–180-word synthetic generations while the existing ASR worker continues. It records
actual elapsed/model usage/digest, periodic GPU-wide memory observations, ASR packet /
audible-source / segment counts, bilingual language observations, lag and errors. It
requires healthy continued capture, fresh English/Bulgarian segments, source evidence,
no added drops/gaps/errors, lag at most five seconds and generation at most sixty
seconds. Existing M5 reserve/pressure admission remains authoritative; overload can
cancel the benchmark. This is not a ninety-minute qualification or a quality score.

Applying a measured profile requires a successful matching run, unchanged model /
configuration fingerprint and explicit human accuracy review, after the session stops.
It locks generation to the actually measured CPU/GPU path and ASR execution device.
No profile is inferred from file existence, GPU branding or fixture data. Defaults stay
8B Q4_K_M, context 4,096, Medium CPU int8, CPU diarization, a 2 GiB reserve and provisional
8 GiB generation allowance. There is no automatic 4B preference or larger context.

Wizard acknowledgement is distinct from qualification. Without a matching successful
profile and complete checks, only explicit limited mode is accepted. Reports keep
blocked/unrun findings visible; acknowledgement always says release_qualified=false.
A stored result is historical evidence. Driver/runtime changes, model tampering,
quality and real sustained performance still require rechecking on the target laptop.
