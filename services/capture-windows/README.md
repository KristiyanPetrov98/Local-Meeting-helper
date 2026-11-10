# Windows audio helper (M3)

.NET 8 / NAudio WASAPI microphone and selected-output loopback capture. No network
listener, files, browser automation or simulated audio. `--list` lists active endpoints.
Otherwise the API supplies a private JSON configuration on inherited stdin, then keeps
the pipe open. PCM packets are JSON/base64 float32 mono 16kHz on stdout; logs never
share that channel. EOF/stop releases devices and flushes the partial packet. A bounded
128-packet output queue reports drops. Default-device changes trigger reconnection.

Build from root using .NET SDK 10.0.403 (global.json):

```powershell
dotnet restore services/capture-windows --locked-mode -r win-x64
dotnet publish services/capture-windows -c Release -r win-x64 --self-contained false --no-restore
```

Keep the whole publish directory together. The API automatically finds its executable;
`PM_CAPTURE_HELPER` is an optional trusted host-path override. .NET 8 runtime is needed
on the target until packaging (M6). Process-specific Chrome loopback is **not** implemented;
selected-output loopback is the explicit fallback. See docs/milestone-3.md.
