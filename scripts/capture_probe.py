"""Windows feasibility probes. Never write audio samples or image frames."""
import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path


def probe(a):
    if os.name != 'nt':
        return {'status': 'blocked_requires_windows', 'mode': a.mode}
    result = {'mode': a.mode, 'status': 'unverified', 'errors': []}
    start = time.monotonic()
    if a.mode in ('devices', 'audio'):
        import pyaudiowpatch as audio
        pa = audio.PyAudio()
        try:
            if a.mode == 'devices':
                return {'status': 'enumerated_not_capture_verified', 'devices': [pa.get_device_info_by_index(i) for i in range(pa.get_device_count())]}
            device = pa.get_device_info_by_index(a.device)
            channels = int(device['maxInputChannels'])
            counters = {'frames': 0, 'callbacks': 0, 'overflow_callbacks': 0, 'non_silent_callbacks': 0, 'max_callback_gap_seconds': 0}
            last = None
            def callback(data, frames, timing, status):
                nonlocal last
                from array import array
                now = time.monotonic()
                if last is not None:
                    counters['max_callback_gap_seconds'] = max(counters['max_callback_gap_seconds'], now-last)
                last = now
                samples = array('f', data)
                rms = math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))
                counters['frames'] += frames
                counters['callbacks'] += 1
                counters['overflow_callbacks'] += int(bool(status))
                counters['non_silent_callbacks'] += int(rms > .001)
                return None, audio.paContinue
            stream = pa.open(format=audio.paFloat32, channels=channels, rate=int(device['defaultSampleRate']), input=True,
                             input_device_index=a.device, frames_per_buffer=1024, stream_callback=callback)
            try:
                time.sleep(a.seconds)
            finally:
                stream.stop_stream(); stream.close()
            result.update(counters=counters, device={'index':a.device,'loopback':device.get('isLoopbackDevice',False)},
                          status='measured_requires_source_isolation_review')
        finally:
            pa.terminate()
    else:
        from windows_capture import WindowsCapture, Frame, InternalCaptureControl
        capture = WindowsCapture(cursor_capture=False, draw_border=True, window_name=a.window)
        counters = {'frames':0,'changed_frames':0,'max_frame_gap_seconds':0}
        last = digest = None
        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            nonlocal last, digest
            now = time.monotonic()
            if last is not None:
                counters['max_frame_gap_seconds'] = max(counters['max_frame_gap_seconds'],now-last)
            last = now
            current = hashlib.sha256(memoryview(frame.frame_buffer).tobytes()).digest()
            counters['changed_frames'] += int(digest is not None and digest != current)
            digest = current
            counters['frames'] += 1
            # No frame, image, or hash persisted.
        @capture.event
        def on_closed():
            result['errors'].append('capture_source_closed')
        control = capture.start_free_threaded()
        try:
            time.sleep(a.seconds)
        finally:
            control.stop()
            control.wait()
        result.update(counters=counters, status='measured_requires_window_isolation_review')
    result['elapsed_seconds'] = time.monotonic()-start
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['devices','audio','window'])
    p.add_argument('--device',type=int,default=-1)
    p.add_argument('--window')
    p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--consent', action='store_true')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    if a.seconds<=0 or (a.mode!='devices' and not a.consent) or (a.mode=='audio' and a.device<0) or (a.mode=='window' and not a.window):
        p.error('explicit consent, positive duration, and exact source required')
    try:
        result=probe(a)
    except Exception as e:
        result={'status':'failed','error_type':type(e).__name__}
    path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'output':str(path)}))
    return 2 if result['status'].startswith(('blocked','failed')) else 0

if __name__=='__main__':
    raise SystemExit(main())
