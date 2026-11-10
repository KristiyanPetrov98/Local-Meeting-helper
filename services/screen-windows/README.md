# Selected-window Windows helper (M5)

Build with .NET SDK 10.0.403 and its bundled Windows SDK reference (minimum Windows 10.0.19041):

```powershell
dotnet restore services/screen-windows --locked-mode -r win-x64
dotnet publish services/screen-windows -c Release -r win-x64 --self-contained false --no-restore
```

Private stdin configuration contains excluded_pids and an explicit enumerated source_id.
With --list, it returns visible window metadata only. Otherwise it captures that HWND
through Windows.Graphics.Capture, revalidates PID/visibility, retains the default OS
border, and emits bounded PNG JSON packets at most twice per second. EOF or another
input line ends capture; the Python owner also kills the process on cancellation.
No monitor fallback, network listener, media files or own-app capture is supported.

The Release Windows binary was cross-built on Linux. Actual WinRT/COM/D3D interop,
window resize/minimize/closure, multi-monitor behavior and display capture exclusion
remain unrun. Follow docs/milestone-5.md on Windows before claiming runtime acceptance.
