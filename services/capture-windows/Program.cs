using System.Diagnostics;
using System.Text.Json;
using System.Threading.Channels;
using NAudio.CoreAudioApi;
using NAudio.CoreAudioApi.Interfaces;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;

// Private inherited stdin/stdout pipes. No network listener and no media files.
if (!OperatingSystem.IsWindows()) { Console.WriteLine("{\"type\":\"error\",\"code\":\"windows_required\"}"); return 2; }
using var devices = new MMDeviceEnumerator();
if (args.Contains("--list")) {
    var found = new List<object>();
    foreach (var flow in new[] { DataFlow.Capture, DataFlow.Render })
        foreach (var device in devices.EnumerateAudioEndPoints(flow, DeviceState.Active)) {
            using (device) found.Add(new { id = device.ID, name = device.FriendlyName, kind = flow == DataFlow.Capture ? "microphone" : "loopback" });
        }
    Console.WriteLine(JsonSerializer.Serialize(new { type = "devices", devices = found, process_loopback = false }));
    return 0;
}
var configLine = await Console.In.ReadLineAsync();
if (configLine is null || configLine.Length > 8192) return 2;
using var config = JsonDocument.Parse(configLine);
var cfg = config.RootElement;
var channel = Channel.CreateBounded<object>(new BoundedChannelOptions(128) { FullMode = BoundedChannelFullMode.Wait, SingleReader = true });
using var done = new CancellationTokenSource();
var clock = Stopwatch.StartNew();
var captures = new List<WasapiCapture>();
var endpoints = new List<MMDevice>();
var flushers = new List<Action>();
long dropped = 0;
void Emit(object value) { if (!channel.Writer.TryWrite(value)) Interlocked.Increment(ref dropped); }
var notifications = new EndpointNotifications(flow => {
    var key = flow == DataFlow.Capture ? "microphone" : "loopback";
    if (cfg.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String && value.GetString() == "default") {
        Emit(new { type = "error", code = "default_device_changed" }); done.Cancel();
    }
});
devices.RegisterEndpointNotificationCallback(notifications);
var writer = Task.Run(async () => {
    await foreach (var message in channel.Reader.ReadAllAsync()) {
        await Console.Out.WriteLineAsync(JsonSerializer.Serialize(message));
        await Console.Out.FlushAsync();
    }
});
void Attach(string key, string source, DataFlow flow) {
    if (!cfg.TryGetProperty(key, out var item) || item.ValueKind == JsonValueKind.Null) return;
    var id = item.GetString();
    var device = id == "default" ? devices.GetDefaultAudioEndpoint(flow, Role.Multimedia) : devices.GetDevice(id!);
    endpoints.Add(device);
    WasapiCapture capture = flow == DataFlow.Capture ? new WasapiCapture(device) : new WasapiLoopbackCapture(device);
    captures.Add(capture);
    var buffer = new BufferedWaveProvider(capture.WaveFormat) { BufferDuration = TimeSpan.FromSeconds(2), ReadFully = false, DiscardOnBufferOverflow = false };
    ISampleProvider mono = new Downmix(buffer.ToSampleProvider());
    var resampler = new WdlResamplingSampleProvider(mono, 16000);
    var pending = new List<float>(3200);
    var scratch = new float[16000];
    long sequence = 0;
    flushers.Add(() => {
        if (pending.Count == 0) return;
        var bytes = new byte[pending.Count * sizeof(float)]; Buffer.BlockCopy(pending.ToArray(), 0, bytes, 0, bytes.Length);
        Emit(new { type = "audio", source, sequence = sequence++, start = Math.Max(0, clock.Elapsed.TotalSeconds - pending.Count / 16000.0), sample_rate = 16000, samples = pending.Count, pcm = Convert.ToBase64String(bytes) });
        pending.Clear();
    });
    capture.DataAvailable += (_, ev) => {
        try {
            buffer.AddSamples(ev.Buffer, 0, ev.BytesRecorded);
            int read;
            while ((read = resampler.Read(scratch, 0, scratch.Length)) > 0) {
                pending.AddRange(scratch.Take(read));
                while (pending.Count >= 1600) {
                    var block = pending.GetRange(0, 1600).ToArray(); pending.RemoveRange(0, 1600);
                    var bytes = new byte[block.Length * sizeof(float)]; Buffer.BlockCopy(block, 0, bytes, 0, bytes.Length);
                    var start = Math.Max(0, clock.Elapsed.TotalSeconds - (pending.Count + block.Length) / 16000.0);
                    Emit(new { type = "audio", source, sequence = sequence++, start, sample_rate = 16000, samples = block.Length, pcm = Convert.ToBase64String(bytes) });
                }
            }
        } catch { Emit(new { type = "error", code = "capture_buffer_or_format_failure", source }); done.Cancel(); }
    };
    capture.RecordingStopped += (_, ev) => {
        if (ev.Exception is not null) { Emit(new { type = "error", code = "device_disconnected", source }); done.Cancel(); }
    };
    capture.StartRecording();
}
try {
    Attach("microphone", "local", DataFlow.Capture);
    Attach("loopback", "remote", DataFlow.Render);
    if (captures.Count == 0) throw new InvalidOperationException();
    Emit(new { type = "started", mode = "selected-output-loopback", sample_rate = 16000 });
    var input = Task.Run(async () => { await Console.In.ReadLineAsync(); done.Cancel(); });
    try { await Task.Delay(Timeout.Infinite, done.Token); } catch (OperationCanceledException) { }
} catch { Emit(new { type = "error", code = "device_start_failed" }); }
finally {
    devices.UnregisterEndpointNotificationCallback(notifications);
    foreach (var capture in captures) { capture.StopRecording(); capture.Dispose(); }
    foreach (var flush in flushers) flush();
    foreach (var endpoint in endpoints) endpoint.Dispose();
    Emit(new { type = "stopped", dropped_packets = Interlocked.Read(ref dropped) });
    channel.Writer.TryComplete();
    // A non-reading parent must not keep recording alive indefinitely.
    await Task.WhenAny(writer, Task.Delay(2000));
}
return 0;

public sealed class Downmix(ISampleProvider source) : ISampleProvider {
    public WaveFormat WaveFormat { get; } = WaveFormat.CreateIeeeFloatWaveFormat(source.WaveFormat.SampleRate, 1);
    private float[] scratch = [];
    public int Read(float[] buffer, int offset, int count) {
        int channels = source.WaveFormat.Channels;
        if (scratch.Length < count * channels) scratch = new float[count * channels];
        int read = source.Read(scratch, 0, count * channels), frames = read / channels;
        for (int i = 0; i < frames; i++) {
            float sum = 0; for (int c = 0; c < channels; c++) sum += scratch[i * channels + c];
            buffer[offset + i] = sum / channels;
        }
        return frames;
    }
}


public sealed class EndpointNotifications(Action<DataFlow> changed) : IMMNotificationClient {
    public void OnDefaultDeviceChanged(DataFlow flow, Role role, string defaultDeviceId) { if (role == Role.Multimedia) changed(flow); }
    public void OnDeviceStateChanged(string deviceId, DeviceState newState) { }
    public void OnDeviceAdded(string deviceId) { }
    public void OnDeviceRemoved(string deviceId) { }
    public void OnPropertyValueChanged(string deviceId, PropertyKey key) { }
}
