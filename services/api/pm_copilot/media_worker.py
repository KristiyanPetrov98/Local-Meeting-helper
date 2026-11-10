"""Private, isolated local-model worker. Never stores PCM, transcripts or model output files."""
import base64
import json
import os
import sys


PROTOCOL = sys.stdout

def emit(data):
    print(json.dumps(data), file=PROTOCOL, flush=True)


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
    config = json.loads(sys.stdin.readline())
    sys.stdout = sys.stderr  # Third-party progress/log output must never corrupt the private protocol.
    import numpy as np
    mode = config['mode']
    if mode == 'asr':
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from faster_whisper import WhisperModel
        model = WhisperModel(config['model_path'], device=config['device'],
                             compute_type='int8_float16' if config['device'] == 'cuda' else 'int8',
                             cpu_threads=config.get('cpu_threads', 8), local_files_only=True)
    else:
        import torch
        from pyannote.audio import Pipeline
        torch.set_num_threads(2)
        model = Pipeline.from_pretrained(config['model_path']).to(torch.device('cpu'))
    emit({'type':'ready'})
    for line in sys.stdin:
        message = json.loads(line)
        try:
            pcm = np.frombuffer(base64.b64decode(message['pcm'], validate=True), dtype='<f4').copy()
            if mode == 'asr':
                segments, info = model.transcribe(pcm, language=config.get('language'), beam_size=5,
                    vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
                result = [{'start':s.start,'end':s.end,'text':s.text.strip(),'words':[{'start':w.start,'end':w.end,'text':w.word} for w in (s.words or [])]} for s in segments
                          if s.text.strip() and s.no_speech_prob < .6]
                emit({'type':'result','segments':result,'language':info.language})
            else:
                output = model({'waveform':torch.from_numpy(pcm).unsqueeze(0),'sample_rate':16000})
                annotation = getattr(output, 'exclusive_speaker_diarization', getattr(output, 'speaker_diarization', output))
                emit({'type':'result','turns':[{'start':turn.start,'end':turn.end,'label':label}
                      for turn, _, label in annotation.itertracks(yield_label=True)]})
        except Exception as error:
            # Do not log exception text that might contain captured content.
            emit({'type':'error','code':type(error).__name__})

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit({'type':'error','code':'worker_start_'+type(error).__name__})
        raise SystemExit(2)
