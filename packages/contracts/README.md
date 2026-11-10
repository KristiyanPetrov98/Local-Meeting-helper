# Process contracts (design, not implemented)

Electron owns lifecycle and per-launch authentication. Capture helper communicates over
an ACL-restricted named pipe, not a TCP capture service. JSON control envelopes have
`version`, `request_id`, `session_id`, `type`, `payload`. Binary frames carry length,
sequence, monotonic timestamp, source ID, PCM format or image dimensions, and payload.
Cap lengths before allocating; reject unsupported versions. Never put media in logs.
Audio: 16 kHz mono float32 per source after resampling; retain original clock metadata.
Screen: transient WGC frame on demand; bounded latest-frame slot. Drop obsolete images.
Events: capture.started/stopped/error, audio.gap, device.changed, transcript.segment,
resource.updated, inference.started/completed/failed. Sequence gaps are visible errors.
Future HTTP/WebSocket: loopback, per-launch bearer token, strict Host/Origin allowlists,
project-scoped IDs; OpenAPI generation in Milestone 1. No unauthenticated API yet.

## M1 implemented additions

`openapi.json` and `src/api.generated.ts` are the current authenticated HTTP schema
and generated types. `src/index.ts` adds the native bridge union and Snapshot aliases.
`state.updated` events are version 1 and carry a complete Snapshot with monotonic
revision. The capture named-pipe design above remains unimplemented until M3.

## M3 implemented additions

AudioOptions, MeetingStatus, transcript pages and speaker edit endpoints are part of
the generated schema. Capture is an explicit per-session opt-in; state.updated carries
lightweight diagnostics, while transcript text uses authenticated scoped pagination.
Private inherited parent/child pipes currently replace the proposed capture named pipe.

## M2 additions

Document metadata, indexing, keyword/hybrid search, typed source citations and
verification routes are included in OpenAPI and generated types. Uploads use a bounded
authenticated octet-stream body, never client filesystem paths.

## M4 additions

Snapshot.assistance reports a single asynchronous manual request. Scoped assistance
POST/history/detail/cancel routes and metadata-only generation diagnostics are typed
in OpenAPI. Validated English briefings contain categorized claims and allowlisted
citation IDs; details resolve citations against current stored sources and separately
report unavailable IDs. NativeStatus includes miniExpanded and assistanceError.

## M5 additions

Snapshot.screen, .sharing and .resources report ephemeral visual/risk state, declared
sharing guards and resource admission. Typed routes enumerate/select windows, return
scoped no-store preview bytes, acknowledge sharing and configure resource settings.
Start.screen/risks are explicit per-session opt-ins. Exclusion is never reported as
verified from a user acknowledgement.

## M6 additions

Snapshot.setup provides setup summary state. Typed setup diagnostics/configuration,
model action, check/benchmark/profile and acknowledgement routes are generated.
Native commands include only fixed setup links and OS-selected approved snapshot
imports. The private import capability is excluded from renderer bootstrap/types.
