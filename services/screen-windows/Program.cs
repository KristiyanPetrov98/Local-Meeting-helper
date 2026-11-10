using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Windows.Graphics.Capture;
using Windows.Graphics.DirectX;
using Windows.Graphics.DirectX.Direct3D11;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

// Separate process, private inherited pipes, no media files or TCP listener.
if (!OperatingSystem.IsWindowsVersionAtLeast(10,0,19041)) return 2;
try {
    if (!GraphicsCaptureSession.IsSupported()) throw new InvalidOperationException();
    var line=await Console.In.ReadLineAsync();
    if (line is null || line.Length>8192) return 2;
    using var document=JsonDocument.Parse(line);var cfg=document.RootElement;
    var excluded=cfg.GetProperty("excluded_pids").EnumerateArray().Select(x=>x.GetUInt32()).ToHashSet();
    excluded.Add((uint)Environment.ProcessId);
    var windows=Native.List(excluded);
    if (args.Contains("--list")) { Console.WriteLine(JsonSerializer.Serialize(new {windows}));return 0; }
    var source=cfg.GetProperty("source_id").GetString();
    var selected=windows.SingleOrDefault(w=>w.id==source) ?? throw new InvalidOperationException();
    using var done=new CancellationTokenSource();
    _=Task.Run(async()=>{await Console.In.ReadLineAsync();done.Cancel();});
    using var device=Native.Device();
    using var factory=WinRT.ActivationFactory.Get("Windows.Graphics.Capture.GraphicsCaptureItem");
    var interop=(ICaptureItemInterop)Marshal.GetObjectForIUnknown(factory.ThisPtr);
    Guid iid=new("79C3F95B-31F7-4EC2-A464-632EF5D30760");
    Marshal.ThrowExceptionForHR(interop.CreateForWindow((nint)selected.hwnd,ref iid,out var pointer));
    var item=WinRT.MarshalInterface<GraphicsCaptureItem>.FromAbi(pointer);Marshal.Release(pointer);
    item.Closed+=(_,_)=>done.Cancel();
    using var pool=Direct3D11CaptureFramePool.CreateFreeThreaded(device,DirectXPixelFormat.B8G8R8A8UIntNormalized,2,item.Size);
    using var session=pool.CreateCaptureSession(item);
    // Keep the OS capture border and cursor visible; never request borderless capture.
    session.StartCapture();
    Console.WriteLine("{\"type\":\"started\"}");
    var size=item.Size;long sequence=0;
    while (!done.IsCancellationRequested) {
        await Task.Delay(500,done.Token);
        if (!Native.Valid(selected,excluded)) throw new InvalidOperationException();
        var frame=pool.TryGetNextFrame();if (frame is null) continue;
        var current=frame.ContentSize;
        if (current.Width<=0 || current.Height<=0) {frame.Dispose();throw new InvalidOperationException();}
        if (current.Width!=size.Width || current.Height!=size.Height) {
            frame.Dispose();size=current;pool.Recreate(device,DirectXPixelFormat.B8G8R8A8UIntNormalized,2,size);continue;
        }
        using var ownedFrame=frame;
        // Readback/scale/encode only in this low-priority process, at most two frames/sec.
        using var bitmap=await SoftwareBitmap.CreateCopyFromSurfaceAsync(frame.Surface);
        using var stream=new InMemoryRandomAccessStream();
        var encoder=await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId,stream);
        encoder.SetSoftwareBitmap(bitmap);
        double scale=Math.Min(1,1024.0/Math.Max(bitmap.PixelWidth,bitmap.PixelHeight));
        encoder.BitmapTransform.ScaledWidth=(uint)Math.Max(1,(int)(bitmap.PixelWidth*scale));
        encoder.BitmapTransform.ScaledHeight=(uint)Math.Max(1,(int)(bitmap.PixelHeight*scale));
        encoder.BitmapTransform.InterpolationMode=BitmapInterpolationMode.Fant;
        await encoder.FlushAsync();
        if (stream.Size>4*1024*1024) throw new InvalidOperationException();
        stream.Seek(0);using var reader=new DataReader(stream.GetInputStreamAt(0));
        await reader.LoadAsync((uint)stream.Size);var bytes=new byte[(int)stream.Size];reader.ReadBytes(bytes);
        await Console.Out.WriteLineAsync(JsonSerializer.Serialize(new {type="frame",source_id=source,sequence=sequence++,png=Convert.ToBase64String(bytes)}));
        await Console.Out.FlushAsync();
    }
} catch (OperationCanceledException) { }
catch { Console.WriteLine("{\"type\":\"error\",\"code\":\"selected_window_capture_failed\"}");return 1; }
return 0;

public record WindowInfo(string id,long hwnd,uint pid,string title);
[ComImport,Guid("3628E81B-3CAC-4C60-B7F4-23CE0E0C3356"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ICaptureItemInterop {
    [PreserveSig] int CreateForWindow(nint window,ref Guid iid,out nint item);
    [PreserveSig] int CreateForMonitor(nint monitor,ref Guid iid,out nint item);
}
static class Native {
    delegate bool EnumProc(nint hwnd,nint value);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc callback,nint value);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int GetWindowText(nint hwnd,StringBuilder text,int max);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(nint hwnd,out uint pid);
    [DllImport("user32.dll")] static extern nint GetShellWindow();
    [DllImport("d3d11.dll")] static extern int D3D11CreateDevice(nint adapter,uint driver,nint software,uint flags,nint levels,uint count,uint sdk,out nint device,out uint level,out nint context);
    [DllImport("d3d11.dll")] static extern int CreateDirect3D11DeviceFromDXGIDevice(nint dxgi,out nint device);
    public static bool Valid(WindowInfo info,HashSet<uint> excluded) {
        var hwnd=(nint)info.hwnd;GetWindowThreadProcessId(hwnd,out uint pid);
        return pid==info.pid && !excluded.Contains(pid) && hwnd!=GetShellWindow() && IsWindowVisible(hwnd) && !IsIconic(hwnd);
    }
    public static List<WindowInfo> List(HashSet<uint> excluded) {
        List<WindowInfo> result=[];
        EnumWindows((hwnd,_)=>{
            GetWindowThreadProcessId(hwnd,out uint pid);var text=new StringBuilder(512);GetWindowText(hwnd,text,512);
            var info=new WindowInfo($"{hwnd}:{pid}",(long)hwnd,pid,text.ToString());
            if (!string.IsNullOrWhiteSpace(info.title) && !info.title.StartsWith("PM Copilot",StringComparison.OrdinalIgnoreCase) && Valid(info,excluded)) result.Add(info);
            return true;
        },0);return result;
    }
    public static IDirect3DDevice Device() {
        Marshal.ThrowExceptionForHR(D3D11CreateDevice(0,1,0,0x20,0,0,7,out var d3d,out _,out var context));
        nint dxgi=0,inspectable=0;
        try {
            var iid=new Guid("54EC77FA-1377-44E6-8C32-88FD5F44C84C");Marshal.ThrowExceptionForHR(Marshal.QueryInterface(d3d,ref iid,out dxgi));
            Marshal.ThrowExceptionForHR(CreateDirect3D11DeviceFromDXGIDevice(dxgi,out inspectable));
            return WinRT.MarshalInterface<IDirect3DDevice>.FromAbi(inspectable);
        } finally {if(inspectable!=0)Marshal.Release(inspectable);if(dxgi!=0)Marshal.Release(dxgi);Marshal.Release(context);Marshal.Release(d3d);}
    }
}
