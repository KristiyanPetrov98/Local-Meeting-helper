# Dashboard and companion (M1 through M6)

One React/Vite/Tailwind client renders the dashboard or mini view. Both receive the
same authenticated API snapshot/events. The service serves production assets; no Vite
server or external assets are needed at runtime. Build with `npm run build:web`.

MeetingPanel contains device/routing configuration, capture diagnostics, transcript
review and session-scoped speaker edits. No production simulated transcript source.

KnowledgePanel provides real upload/drag-drop, source indexing, scoped search,
revision/citation previews and document deletion. See docs/milestone-2.md.

AssistancePanel supports explicit requests, cancellation, live progress, question
suppression, English categorized briefings, citation previews and session history.
The same component renders a compact companion view. No production fake answer mode.

ScreenPanel adds explicit sharing/window controls, revocable RAM previews, resource
settings and potential-risk evidence. A session preserves its declared sharing mode.
No M5 images/findings are stored in browser persistence.

SetupPanel is a non-blocking wizard for diagnostics, approved model actions, real
offline checks, live evidence and short device measurements. Completed operations
are distinct from passed checks. Limited completion is explicit.
