# M7 integration, privacy and qualification architecture

M7 extends M1–M6; the same Electron process, FastAPI service, project-scoped SQLite database, isolated workers and local Ollama endpoints remain in use. No cloud inference, fallback model or automatic meeting answering was introduced.

## HTTP and event boundaries

The existing loopback bind, per-launch bearer, exact Host/Origin checks, private desktop import capability, isolated renderer and content security policy remain. Credentials are compared as bytes so malformed Unicode credentials are rejected instead of raising a server error. HTTP denials now carry the same no-store/security headers as other responses.

The API limits ordinary request bodies to 64 KiB, checking both declared size and received bytes. Only the existing POST document-upload route with octet-stream content retains its separate 20 MiB ceiling. A changed content type does not lift another route's limit. Validation responses omit input and exception context: failed token fields and malformed JSON cannot be echoed in a 422 response. Errors still identify fields/types. The event socket requires a bounded text JSON object containing a string token. Binary frames, malformed credentials and subsequent client commands close with policy code 1008. Its latest-state queue remains bounded to one snapshot per listener.

These tests establish the tested loopback boundaries. They do not protect a compromised OS account, encrypt the local SQLite database, or prove model output factually follows a citation. Transcript text, documents and requested answers are deliberately local persistent data; raw media is transient.

## Citation cache correctness and cost

Previously, source verification could use an outdated cached revision if its parsed source was changed through another SQLite connection. `document_revisions.source_epoch` is an additive migration. An SQLite trigger increments it whenever the source units change. The authorized citation query fetches that epoch, invalidating an old entry before comparing exact source text, locator, text hash and citation ID. Warm-cache corruption and restart tests exercise this behavior.

The cache retains at most four revisions and 32 MiB of accounted Python objects, including source strings, locator objects and packed newline indexes. A single oversized entry is verified without retention. Text line offsets use binary search over packed newline positions instead of repeatedly allocating/scanning a prefix. Deleting knowledge clears both the cache and its accounting. Source data, newline indexes and authorization are never shared across unauthorized project queries.

The retained-object limit is not a process RSS limit: allocator overhead, temporary parsing data and workers are separate. The before/after benchmark uses the actual parser and store, not a mock citation implementation. Its small differences should not be generalized to GPU or model latency.

## Long-run target recorder

`Qualification` is an explicit in-memory observer, exposed through authenticated `/api/qualification` routes and the setup wizard's Device benchmark page. Starting requires active consented transcription, Windows, a single RTX 4080 Laptop GPU, a GPU generation profile and an available primary model identity. There is no production fixture switch or accelerated-duration parameter.

Every two seconds it samples existing capture counters, queue depth, last completed ASR chunk lag, actual NVIDIA memory totals/free memory, primary Ollama residency and backend working-set memory. Sampling has a 3,000-entry bound. It records source identity, model digest and initial configuration. Changed configuration/GPU/session, telemetry gaps over six seconds or interrupted capture fail the check. At least 90 minutes must have been observed with capture active. The operator must stop the session before finishing so native dropped-packet counters and final transcription are included. Missing native final counters or a capture shutdown error cannot pass.

Finishing aggregates actual manual-request latency/statuses and observed languages, checks no-question suppression, verifies every referenced document citation again and detects changed response model digests. A completed report can still fail. Reports contain metadata/counters, not transcript text, generated answers, project titles, images, PCM, credentials or device paths. Cancel/quit discards an unfinished run. Nothing silently starts capture or model generation.

ASR lag percentiles describe sampled last-completed-chunk lag, not independent per-chunk latency observations. GPU usage includes other processes. Backend RSS excludes native/audio/model workers; separate worker-memory review remains required. Language detection and energy observations do not establish transcription accuracy. Human checks cover content quality, both audio arrangements, screen relevance, discreet risks, sharing preview, offline use, privacy, restarts and clean installation.

## Evidence identity and release decision

`build_identity.py` hashes executable source, tests, scripts, contracts, locks, workflows and packaging configuration/licenses in sorted path order. Generated outputs, caches, reports and documentation are excluded. The PyInstaller build embeds this identity; notice manifests and target recordings carry it. Changing a model/configuration invalidates that recording; changing hashed source requires new evidence/builds. The digest identifies inputs, not reproducible binary equality or a cryptographic attestation of test execution.

`scripts/qualify-release.py` requires matching portable checks, clean dependency scans, completed target telemetry, a Windows build/smoke report, the actual installer hash and explicit operator review. Missing/short/stale/false/string-boolean evidence blocks release. The command exits 2 for a blocked release and 0 only when every gate passes. It neither signs nor publishes. Operator review is an attestation, not an independent audit. The checked-in cloud decision is blocked.

## Dependency remediation

The initial audit found vulnerable pypdf 6.1.3, pytest 8.4.2, Torch 2.8.0 and minimatch 9/10 build dependencies. M7 pins pypdf 6.21.4 and pytest 9.2.0, and regenerates hashed locks. Scoped minimatch 11.0.1 overrides affect the Electron builder consumers, preserving old callable minimatch versions used by unrelated dependencies. Packaging is exercised after the override.

The Windows CPU diarization lock now resolves pyannote.audio 4.0.7, Torch 2.15.0, torchaudio 2.11.1 and TorchCodec 0.17.0 for Python 3.12/Windows x64 against the existing ASR constraints. Upstream TorchCodec's compatibility table lists 0.17 with Torch >=2.11. Resolution/advisory checks pass, but these Windows wheels have not been imported or exercised here. The Windows bundle smoke requires actual pyannote import; full diarization/model quality remains a release gate. Do not describe resolution as runtime compatibility verification.

Native helpers move from .NET 8 (end of support 2026-11-10) to .NET 10 LTS, SDK 10.0.403/runtime 10.0.14 (support through 2028-11-14 per Microsoft's release metadata). The SDK tarball was SHA-512 checked against official metadata before use. Framework paths, global SDK pin, workflows, locks, setup documentation and runtime licenses/notices are updated. Windows SDK references come from that pinned SDK. Self-contained win-x64 builds and the three conversion tests ran on Linux; Windows execution is unverified.

PyPI advisory auditing covers all pinned lock files, including Windows-only packages, through the PyPI version API. A network/version lookup error is incomplete evidence. npm and NuGet scans use their published feeds. A clean dated scan establishes absence of reported advisories in those feeds at scan time, not absence of vulnerabilities or license obligations. Native runtime licenses/notices come from dotnet/runtime v10.0.14. Existing per-model license/access acknowledgements remain required.
