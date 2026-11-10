import asyncio
import base64
import importlib.util
import json
import os
import sys
import time
from array import array
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .audio import Chunks, SpeakerStitcher, packet, RATE
from .store import DomainError
from .runtime import command, cwd, hidden_flags

ROOT = Path(__file__).resolve().parents[3]


class AudioOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    microphone: str | None = Field(default='default', max_length=1024)
    loopback: str | None = Field(default='default', max_length=1024)
    language: Literal['auto','en','bg'] = 'auto'
    device: Literal['cpu','cuda'] = 'cpu'
    echo_profile: Literal['headphones','speakers'] = 'headphones'
    diarization: bool = False


class Meeting:
    def __init__(self, notify, segment, refine):
        self.notify, self.segment, self.refine = notify, segment, refine
        self.helper = Path(os.environ.get('PM_CAPTURE_HELPER', str(ROOT/'services/capture-windows/bin/Release/net10.0-windows/win-x64/publish/PmCopilot.Capture.exe')))
        self.model = Path(os.environ.get('PM_WHISPER_MODEL', str(ROOT/'models/runtime/whisper-medium')))
        self.diar_model = Path(os.environ.get('PM_DIARIZATION_MODEL', str(ROOT/'models/runtime/community-1')))
        self.tasks = []
        self.processes = []
        self.state = 'idle'
        self.error = None
        self.counts = {}
        self.session_id = None
        self.epoch = 0
        self.options = AudioOptions()
        self.optional_busy=lambda:False
        self.queue = asyncio.Queue(maxsize=8)
        self.diar_queue = asyncio.Queue(maxsize=1)
        self.chunks = {}
        self.stitcher = SpeakerStitcher()
        self.stopping = False

    def diagnostics(self):
        reason = None
        if sys.platform != 'win32': reason = 'Windows 11 is required for WASAPI capture'
        elif not self.helper.is_file(): reason = 'Build the Windows capture helper first'
        elif not self.model.is_dir(): reason = 'Install multilingual Whisper Medium locally and set PM_WHISPER_MODEL'
        elif importlib.util.find_spec('faster_whisper') is None: reason = 'Install the M3 ASR dependencies into the API virtual environment'
        return {'available':reason is None,'reason':reason,'process_loopback':False,
                'diarization_model_present':self.diar_model.is_dir()}

    def status(self):
        return {**self.diagnostics(),'state':self.state,'error':self.error,'session_id':self.session_id,
                'counts':dict(self.counts),'queue_depth':self.queue.qsize()}

    async def enumerate_devices(self):
        if sys.platform != 'win32' or not self.helper.is_file():
            return {'devices':[],'reason':self.diagnostics()['reason'],'process_loopback':False}
        process = await asyncio.create_subprocess_exec(str(self.helper),'--list',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,creationflags=hidden_flags())
        try:
            output,_ = await asyncio.wait_for(process.communicate(),10)
            if process.returncode: raise DomainError('Windows audio device enumeration failed',503)
            return json.loads(output)
        except (ValueError,asyncio.TimeoutError):
            if process.returncode is None: process.kill();await process.wait()
            raise DomainError('Windows audio device enumeration failed',503)

    def preflight(self, options):
        diag = self.diagnostics()
        if not diag['available']: raise DomainError(diag['reason'],503)
        if not options.microphone and not options.loopback: raise DomainError('Select at least one audio source',422)
        if options.diarization and (not self.diar_model.is_dir() or importlib.util.find_spec('pyannote') is None):
            raise DomainError('Community-1 offline assets and pyannote dependencies are required for diarization',503)

    async def begin(self, session_id, options, started_at):
        same_session = self.session_id == session_id
        previous_counts = dict(self.counts) if same_session else None
        previous_stitcher = self.stitcher if same_session else None
        await self.stop(flush=False)
        self.options, self.session_id = options, session_id
        self.asr_device = options.device
        self.state, self.error, self.stopping = 'starting', None, False
        self.offset_origin = time.monotonic() - max(0,time.time()-__import__('datetime').datetime.fromisoformat(started_at).timestamp())
        self.counts = {'packets':0,'gaps':0,'dropped_chunks':0,'segments':0,'asr_errors':0,'reconnects':0,'diarization_errors':0}
        if previous_counts: self.counts.update(previous_counts)
        self.queue = asyncio.Queue(maxsize=8);self.diar_queue = asyncio.Queue(maxsize=1)
        self.chunks = {s:Chunks(overlap_seconds=.5,silence_seconds=.6) for s in ('local','remote')}
        self.diar_audio = bytearray();self.diar_start = None
        self.stitcher = previous_stitcher or SpeakerStitcher()
        self.last_word_end = {'local':0.,'remote':0.}
        epoch = self.epoch
        self.tasks.append(asyncio.create_task(self._initialize(epoch)))
        await self.notify()

    async def _spawn_worker(self, mode):
        process = await asyncio.create_subprocess_exec(*command('media'),cwd=cwd(),stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=1048576,
            creationflags=hidden_flags(background=mode=='diarization'))
        self.processes.append(process)
        cfg = {'mode':mode,'model_path':str(self.model if mode=='asr' else self.diar_model),
               'device':getattr(self,'asr_device',self.options.device),'language':None if self.options.language=='auto' else self.options.language}
        process.stdin.write((json.dumps(cfg)+'\n').encode());await process.stdin.drain()
        message = json.loads(await asyncio.wait_for(process.stdout.readline(),120))
        if message.get('type') != 'ready': raise RuntimeError('model_worker_not_ready')
        return process

    async def _initialize(self, epoch):
        try:
            asr = await self._spawn_worker('asr')
            self.counts['asr_cuda_active']=int(self.asr_device=='cuda')
            self.tasks.append(asyncio.create_task(self._asr_loop(asr,epoch)))
            if self.options.diarization:
                self.tasks.append(asyncio.create_task(self._diarize_loop(epoch)))
            self.capture_task=asyncio.create_task(self._capture_loop(epoch))
            self.tasks.append(self.capture_task)
            self.tasks.append(asyncio.create_task(self._health(epoch)))
        except asyncio.CancelledError: raise
        except Exception:
            self.state, self.error = 'error','Local Whisper worker failed to load. Check the model directory and CPU/CUDA runtime.'
            for process in self.processes:
                if process.returncode is None: process.kill()
            await self.notify()

    async def _health(self, epoch):
        while epoch==self.epoch:
            await asyncio.sleep(1)
            await self.notify()

    async def _capture_loop(self, epoch):
        failures = 0
        while epoch==self.epoch and not self.stopping:
            process = None
            healthy_since = None
            try:
                process = await asyncio.create_subprocess_exec(str(self.helper),stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=20000,creationflags=hidden_flags())
                self.processes.append(process)
                self.capture_process = process
                cfg = {'microphone':self.options.microphone,'loopback':self.options.loopback}
                process.stdin.write((json.dumps(cfg)+'\n').encode());await process.stdin.drain()
                offset = time.monotonic()-self.offset_origin
                # A fresh helper has fresh source sequences. Clear discontinuous tails.
                self.chunks = {s:Chunks(overlap_seconds=.5,silence_seconds=.6) for s in ('local','remote')}
                while epoch==self.epoch:
                    line = await process.stdout.readline()
                    if not line: raise RuntimeError('capture_ended')
                    event = json.loads(line)
                    if event.get('type')=='started':
                        healthy_since = time.monotonic()
                        self.state = 'capturing';await self.notify()
                    elif event.get('type')=='audio':
                        source,sequence,start,pcm = packet(event)
                        self.counts['packets']+=1
                        self.counts[source+'_packets']=self.counts.get(source+'_packets',0)+1
                        levels=array('f');levels.frombytes(pcm)
                        audible=bool(levels) and sum(x*x for x in levels)/len(levels)>1e-7
                        if audible:
                            self.counts[source+'_audible_packets']=self.counts.get(source+'_audible_packets',0)+1
                        chunks,gap = self.chunks[source].push(sequence,start+offset,pcm,audible=audible)
                        if gap:
                            self.counts['gaps']+=1
                            self.error = 'Audio discontinuity observed; review the transcript for missing speech.'
                        for chunk in chunks: self._enqueue(source,*chunk)
                        if source=='remote' and self.options.diarization: self._diar_audio(start+offset,pcm,gap)
                    elif event.get('type')=='stopped':
                        self.counts['native_dropped_packets']=int(event.get('dropped_packets',0))
                        break
                    elif event.get('type')=='error': raise RuntimeError('device_error')
                return
            except asyncio.CancelledError: raise
            except Exception:
                if self.stopping: return
                if healthy_since and time.monotonic()-healthy_since>30: failures=0
                failures+=1;self.counts['reconnects']+=1
                self.state, self.error = 'reconnecting','Audio device failed. Reconnecting to the selected device; missing audio is not recoverable.'
                await self.notify()
                if failures>=5:
                    self.state='error';self.error='Audio recovery exhausted. Check devices and use Retry capture.';await self.notify();return
                await asyncio.sleep(min(5,failures))
            finally:
                if process and process.returncode is None:
                    process.kill();await process.wait()
                if process in self.processes: self.processes.remove(process)

    def _enqueue(self, source, start, pcm):
        if not pcm: return
        try: self.queue.put_nowait((source,start,pcm))
        except asyncio.QueueFull:
            self.counts['dropped_chunks']+=1
            self.error = 'Transcription cannot keep up. An audio chunk was dropped from the bounded RAM queue; capture is continuing.'

    async def _request(self, process, pcm, timeout=120):
        process.stdin.write((json.dumps({'pcm':base64.b64encode(pcm).decode()})+'\n').encode())
        await process.stdin.drain()
        line = await asyncio.wait_for(process.stdout.readline(),timeout)
        result = json.loads(line)
        if result.get('type') != 'result': raise RuntimeError('model_inference_failed')
        return result

    async def _asr_loop(self, process, epoch):
        recoveries = 0
        while epoch==self.epoch:
            item = await self.queue.get()
            try:
                source,start,pcm = item
                samples = array('f');samples.frombytes(pcm)
                if samples and sum(x*x for x in samples)/len(samples)<1e-7: continue
                t0 = time.monotonic()
                duration=len(pcm)/4/RATE
                self.counts['last_collection_ms']=round(duration*1000)
                self.counts['last_queue_wait_ms']=round(max(0,t0-self.offset_origin-start-duration)*1000)
                result = await self._request(process,pcm)
                self.counts['last_asr_ms']=round((time.monotonic()-t0)*1000)
                self.counts['last_asr_rtf_milli']=round(self.counts['last_asr_ms']/max(.001,duration))
                self.counts['last_chunk_lag_ms']=round(max(0,time.monotonic()-self.offset_origin-start-len(pcm)/4/RATE)*1000)
                if epoch != self.epoch: return
                for i,segment in enumerate(result['segments']):
                    begin,end = start+max(0,segment['start']),min(start+len(pcm)/4/RATE,start+segment['end'])
                    text = segment['text']
                    if segment.get('words'):
                        words = [w for w in segment['words'] if start+w['end']>self.last_word_end[source]+.05]
                        if not words: continue
                        begin = max(begin,start+words[0]['start'])
                        end = min(end,start+words[-1]['end'])
                        text = ''.join(w['text'] for w in words).strip()
                    elif end<=self.last_word_end[source]: continue
                    if begin>=end or not text: continue
                    self.last_word_end[source] = end
                    await self.segment(self.session_id,source,begin,end,text,result['language'],f'{start:.5f}:{i}',self.options.echo_profile=='speakers')
                    self.counts['last_speech_delay_ms']=round(max(0,time.monotonic()-self.offset_origin-end)*1000)
                    self.counts['segments']+=1
            except asyncio.CancelledError: raise
            except Exception:
                recoveries+=1
                self.counts['asr_errors']+=1
                self.counts['dropped_chunks']=self.counts.get('dropped_chunks',0)+1
                self.error='Whisper failed; audio capture continues in bounded RAM. Retrying ASR on CPU; missing chunks are counted.'
                await self.notify()
                # Never stop capture merely because inference/OOM failed. Never reuse late worker responses.
                if process.returncode is None: process.kill();await process.wait()
                if process in self.processes: self.processes.remove(process)
                if self.stopping or recoveries>=3:
                    self.error='ASR recovery exhausted. Audio capture continues, but transcription requires Retry capture.'
                    await self.notify();return
                self.asr_device='cpu';self.counts['asr_cpu_fallback']=1
                self.counts['asr_cuda_active']=0
                try: process=await self._spawn_worker('asr')
                except asyncio.CancelledError: raise
                except Exception:
                    self.error='CPU ASR restart failed. Capture continues; check the runtime and use Retry capture.'
                    await self.notify();return
            finally: self.queue.task_done()

    def _diar_audio(self, start, pcm, gap):
        if gap: self.diar_audio.clear();self.diar_start=None
        if self.diar_start is None: self.diar_start=start
        self.diar_audio.extend(pcm)
        size = 30*RATE*4
        if len(self.diar_audio)>=size:
            item=(self.diar_start,bytes(self.diar_audio[:size]))
            if not self.diar_queue.full(): self.diar_queue.put_nowait(item)
            # Keep 10 seconds for temporal-overlap provisional label alignment.
            del self.diar_audio[:20*RATE*4];self.diar_start+=20

    async def _diarize_loop(self, epoch):
        try:
            process = await self._spawn_worker('diarization')
            while epoch==self.epoch:
                start,pcm = await self.diar_queue.get()
                try:
                    # Refinement is lower priority than a growing transcription queue.
                    if self.queue.qsize()>1 or self.optional_busy(): continue
                    result = await self._request(process,pcm,180)
                    if epoch==self.epoch:
                        turns = self.stitcher.assign(result['turns'],start)
                        await self.refine(self.session_id,turns)
                finally: self.diar_queue.task_done()
        except asyncio.CancelledError: raise
        except Exception:
            self.counts['diarization_errors']+=1
            self.error='Speaker refinement failed; transcription continues with unrefined labels.'
            await self.notify()

    async def stop(self, flush=True):
        self.stopping = True
        process = getattr(self,'capture_process',None)
        if process and process.returncode is None:
            try:
                process.stdin.write(b'\n');await process.stdin.drain()
                task=getattr(self,'capture_task',None)
                if task: await asyncio.wait_for(asyncio.shield(task),3)
            except (asyncio.TimeoutError,BrokenPipeError,ConnectionResetError):
                self.error='Capture shutdown timed out; the final native buffer may be incomplete.'
            if process.returncode is None:
                process.kill();await process.wait()
        if flush and self.state in ('capturing','reconnecting'):
            for source,chunks in self.chunks.items():
                tail = chunks.flush()
                if tail: self._enqueue(source,*tail)
            self.state='finishing';await self.notify()
            try: await asyncio.wait_for(self.queue.join(),30)
            except asyncio.TimeoutError: self.error='Final transcription deadline exceeded; some final speech may be missing.'
        self.epoch+=1
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        self.tasks.clear()
        for process in self.processes:
            if process.returncode is None: process.kill()
            await process.wait()
        self.processes.clear()
        self.chunks.clear()
        self.queue = asyncio.Queue(maxsize=8);self.diar_queue = asyncio.Queue(maxsize=1)
        if hasattr(self,'diar_audio'): self.diar_audio.clear()
        self.state='idle'
        await self.notify()
