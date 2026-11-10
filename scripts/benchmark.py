"""Local-only M0 measurements. JSON contains metrics, never captured content."""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import platform
import queue
import shutil
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return {'exit_code': p.returncode, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error': type(e).__name__}


def inventory():
    return {'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'os': platform.platform(), 'python': platform.python_version(),
            'gpu': command(['nvidia-smi', '--query-gpu=name,uuid,memory.total,memory.free,driver_version,power.limit', '--format=csv']),
            'ollama': command(['ollama', '--version']),
            'dotnet': command(['dotnet', '--version']),
            'node': command(['node', '--version']),
            'ram': command(['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory']) if os.name == 'nt' else command(['free', '-b']),
            'cpu_count': os.cpu_count()}


def api(path, body=None):
    # Fixed loopback destination; ignore inherited outbound proxies for local inference.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('http://127.0.0.1:11434/api/' + path,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    return opener.open(req, timeout=180)


def summary(values):
    if not values:
        return {'count': 0, 'median': None, 'p95': None, 'max': None}
    ordered = sorted(values)
    return {'count': len(values), 'median': statistics.median(values),
            'p95': ordered[min(len(ordered)-1, __import__('math').ceil(.95*len(ordered))-1)], 'max': max(values)}


def run(a):
    out = {'inventory': inventory(), 'config': vars(a).copy(), 'errors': [], 'status': 'unverified'}
    out['config'].pop('output', None)
    # Fail before loading anything if the intended hardware isn't available.
    gpu = out['inventory']['gpu']
    if gpu.get('exit_code') != 0:
        out['status'] = 'blocked_no_nvidia_smi'
        return out
    try:
        with api('tags') as response:
            tags = json.load(response)['models']
        model = next(x for x in tags if x['name'] == a.model or x.get('model') == a.model)
        out['model_identity'] = {k: model.get(k) for k in ('name', 'digest', 'size', 'details')}
    except Exception as e:
        out['status'] = 'blocked_ollama_or_model'
        out['errors'].append(type(e).__name__)
        return out
    samples, latencies, ttfts, asr_times, lags, errors = [], [], [], [], [], out['errors']
    stop = threading.Event()
    asr_queue = queue.Queue(maxsize=4)
    counters = {'audio_chunks': 0, 'queue_drops': 0, 'audio_overflows': 0, 'asr_completed': 0, 'llm_completed': 0}
    threads = []

    def telemetry():
        while not stop.is_set():
            result = command(['nvidia-smi', '--query-gpu=memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw', '--format=csv,noheader,nounits'])
            try:
                rows = list(csv.reader(result['stdout'].splitlines()))
                samples.append({'seconds': time.monotonic()-started, 'gpus': [[float(v.strip()) for v in row] for row in rows]})
            except (KeyError, ValueError):
                errors.append('telemetry_sample_failed')
            stop.wait(.5)

    def transcribe():
        while not stop.is_set() or not asr_queue.empty():
            try:
                stamp, audio, rate = asr_queue.get(timeout=.2)
            except queue.Empty:
                continue
            t = time.monotonic()
            try:
                from faster_whisper.audio import decode_audio
                import wave
                buffer = io.BytesIO()
                with wave.open(buffer, 'wb') as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
                    w.writeframes((np.clip(audio, -1, 1)*32767).astype(np.int16).tobytes())
                buffer.seek(0)
                pcm = decode_audio(buffer, sampling_rate=16000)
                segments, _ = whisper.transcribe(pcm, language=a.language, beam_size=5)
                # Consume lazy generator; discard text to avoid transcript persistence.
                for _ in segments:
                    pass
                asr_times.append(time.monotonic()-t)
                lags.append(time.monotonic()-stamp)
                counters['asr_completed'] += 1
            except Exception as e:
                errors.append('asr:' + type(e).__name__)
            finally:
                asr_queue.task_done()

    stream = pa = None
    try:
        if a.asr != 'none':
            if os.name != 'nt':
                raise RuntimeError('live_ASR_requires_Windows_PyAudioWPatch')
            import numpy as np
            import pyaudiowpatch as pyaudio
            from faster_whisper import WhisperModel
            whisper = WhisperModel(a.whisper_model, device=a.asr, compute_type='int8_float16' if a.asr == 'cuda' else 'int8', local_files_only=True, cpu_threads=a.cpu_threads)
            pa = pyaudio.PyAudio()
            device = pa.get_device_info_by_index(a.audio_device)
            rate = int(device['defaultSampleRate'])
            channels = int(device['maxInputChannels'])
            if channels < 1:
                raise RuntimeError('not_an_input_or_loopback_device')
            # Fixed five-second blocks; resample in memory, never write media.
            import collections
            chunks = collections.deque()
            size = 0
            def callback(data, frames, info, status):
                nonlocal size
                if status:
                    counters['audio_overflows'] += 1
                mono = np.frombuffer(data, dtype=np.float32).reshape(-1, channels).mean(axis=1)
                chunks.append(mono)
                size += len(mono)
                if size >= rate*5:
                    audio = np.concatenate(chunks)
                    chunks.clear()
                    size = 0
                    counters['audio_chunks'] += 1
                    try:
                        asr_queue.put_nowait((time.monotonic(), audio, rate))
                    except queue.Full:
                        counters['queue_drops'] += 1
                return (None, pyaudio.paContinue)
            stream = pa.open(format=pyaudio.paFloat32, channels=channels, rate=rate, input=True,
                             input_device_index=a.audio_device, frames_per_buffer=1024, stream_callback=callback, start=False)
        started = time.monotonic()
        threads.append(threading.Thread(target=telemetry))
        if stream:
            threads.append(threading.Thread(target=transcribe))
        for t in threads:
            t.start()
        if stream:
            stream.start_stream()
        # Warm-up is recorded separately and excluded from latency summary.
        out['requests'] = []
        while time.monotonic()-started < a.seconds:
            if a.asr_only:
                stop.wait(.2)
                continue
            t0 = time.monotonic()
            first = None
            body = {'model': a.model, 'prompt': ('Synthetic project fact: continuous transcription has higher priority than optional vision.\n' * a.prompt_repetitions) + 'Explain the tradeoffs of local meeting transcription in three concise points.',
                    'stream': True, 'keep_alive': '10m', 'options': {'num_ctx': a.context, 'num_predict': 128, 'temperature': 0}}
            if a.image:
                # Explicit synthetic fixture only; never save captured screenshots.
                body['images'] = [base64.b64encode(Path(a.image).read_bytes()).decode()]
            try:
                done = None
                with api('generate', body) as response:
                    for line in response:
                        event = json.loads(line)
                        if event.get('response') and first is None:
                            first = time.monotonic()-t0
                        if event.get('error'):
                            raise RuntimeError('ollama_inference_error')
                        if event.get('done'):
                            done = event
                if done is None:
                    raise RuntimeError('missing_done_event')
                elapsed = time.monotonic()-t0
                record = {k: done.get(k) for k in ('load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration','done_reason')}
                record.update(seconds=elapsed, ttft_seconds=first, warmup=not out['requests'])
                out['requests'].append(record)
                counters['llm_completed'] += 1
                if not record['warmup']:
                    latencies.append(elapsed)
                    if first is not None:
                        ttfts.append(first)
                if elapsed > 60:
                    errors.append('generation_over_60_seconds')
                with api('ps') as response:
                    out['ollama_residency'] = json.load(response)
            except Exception as e:
                errors.append('llm:' + type(e).__name__)
                break
            stop.wait(min(a.interval, max(0, a.seconds-(time.monotonic()-started))))
    except Exception as e:
        errors.append('setup:' + type(e).__name__ + ':' + str(e)[:120])
    finally:
        if stream:
            stream.stop_stream(); stream.close()
        if pa:
            pa.terminate()
        stop.set()
        for t in threads:
            t.join()
        try:
            with api('generate', {'model': a.model, 'keep_alive': 0}) as response:
                response.read()
        except Exception:
            errors.append('model_unload_failed')
    free = [g[1] for s in samples for g in s['gpus']]
    used = [g[0] for s in samples for g in s['gpus']]
    out.update(counters=counters, telemetry=samples, generation_seconds=summary(latencies), ttft_seconds=summary(ttfts),
               asr_processing_seconds=summary(asr_times), asr_chunk_end_lag_seconds=summary(lags),
               min_free_mib=min(free) if free else None, peak_used_mib=max(used) if used else None,
               elapsed_seconds=time.monotonic()-started if 'started' in locals() else 0)
    if not samples:
        errors.append('no_gpu_samples')
    if not a.asr_only and not latencies:
        errors.append('no_post_warmup_generation_measurements')
    if a.asr != 'none' and not asr_times:
        errors.append('no_completed_transcription')
    if lags and statistics.median(lags) >= 5:
        errors.append('median_chunk_end_lag_at_least_5_seconds')
    failed = bool(errors or counters['queue_drops'] or counters['audio_overflows'] or (free and min(free)<2048))
    out['status'] = 'failed' if failed else 'measured_requires_review'
    out['qualification'] = 'Never a laptop acceptance pass automatically. Review identity, quality, live capture evidence, backlog, reserve, run duration and thermal stability.'
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['inventory', 'run'])
    p.add_argument('--output', required=True)
    p.add_argument('--model', default='qwen3-vl:8b-instruct-q4_K_M')
    p.add_argument('--context', type=int, choices=[4096,6144,8192], default=4096)
    p.add_argument('--seconds', type=int, default=300)
    p.add_argument('--interval', type=float, default=10)
    p.add_argument('--asr', choices=['none','cuda','cpu'], default='none')
    p.add_argument('--consent', action='store_true', help='Confirm recording consent before live audio capture')
    p.add_argument('--asr-only', action='store_true')
    p.add_argument('--audio-device', type=int, default=-1)
    p.add_argument('--language', choices=['en','bg'], default='en')
    p.add_argument('--whisper-model', default='medium')
    p.add_argument('--cpu-threads', type=int, default=8)
    p.add_argument('--prompt-repetitions', type=int, default=1, help='Synthetic context load; verify actual prompt_eval_count')
    p.add_argument('--image', help='Optional synthetic, non-sensitive vision fixture')
    a = p.parse_args()
    if a.asr != 'none' and not a.consent:
        p.error('live audio requires --consent')
    if a.asr_only and a.asr == 'none':
        p.error('--asr-only requires --asr')
    if a.prompt_repetitions < 1:
        p.error('positive synthetic prompt repetitions required')
    if a.seconds <= 0 or a.interval < 0 or (a.asr != 'none' and a.audio_device < 0):
        p.error('positive duration, nonnegative interval and explicit ASR input device required')
    result = inventory() if a.mode == 'inventory' else run(a)
    dest = Path(a.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(dest), 'status': result.get('status', 'inventory_recorded')}))
    return 2 if result.get('status','').startswith(('blocked', 'failed')) else 0

if __name__ == '__main__':
    raise SystemExit(main())
