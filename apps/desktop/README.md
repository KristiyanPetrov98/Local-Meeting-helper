# Electron shell (M1)

Main/preload TypeScript is bundled by `npm run build:desktop`. Main owns the Python
service, tray, windows, global shortcut and process shutdown. Run `npm start` from root
after building. See docs/milestone-1.md for native verification limits.

M4 connects the actual global shortcut to the asynchronous scoped assistance API,
coalesces repeated triggers, expands the mini window, and exposes native errors.
UI/manual requests share the backend single-flight limit. See docs/milestone-4.md.

M5 guards every companion show against the API's declared sharing mode, checks it
every 250 ms, and requests content protection on both windows. The user must declare
broader sharing before using Meet's picker. See docs/milestone-5.md; OS exclusion
is not verified.

M6 resolves packaged resources and starts a bundled backend executable. Model import
uses a trusted OS folder picker and a separate capability never exposed in bootstrap.
See docs/milestone-6.md; Windows installer build/install remains unqualified.
