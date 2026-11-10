"""Local resource admission. Never stops capture or acquires an ASR worker lock."""
from .ollama_http import ollama_client
import asyncio
import csv
import io
import json
import shutil
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
import httpx
from pydantic import BaseModel,ConfigDict,Field
from .briefing import MODEL

PROFILE=ContextVar('ollama_execution_profile',default=None)

class ResourceDeferred(RuntimeError):pass

class ResourceSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reserve_mib:int=Field(default=2048,ge=1024,le=8192)
    generation_budget_mib:int=Field(default=8192,ge=4096,le=16384)
    force_cpu:bool=False


class LocalProbe:
    async def sample(self):
        gpus=[];reason=None;resident=[]
        executable=shutil.which('nvidia-smi')
        if executable:
            process=await asyncio.create_subprocess_exec(executable,'--query-gpu=uuid,name,memory.total,memory.free','--format=csv,noheader,nounits',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            try:
                output,_=await asyncio.wait_for(process.communicate(),2)
                if process.returncode:raise ValueError()
                for uuid,name,total,free in csv.reader(io.StringIO(output.decode())):
                    total,free=int(total.strip()),int(free.strip())
                    if not 0<=free<=total:raise ValueError()
                    gpus.append(dict(uuid=uuid.strip(),name=name.strip(),total_mib=total,free_mib=free))
            except (TimeoutError,ValueError,UnicodeError):
                gpus=[];reason='NVIDIA memory probe failed; GPU admission is disabled.'
            finally:
                if process.returncode is None:process.kill();await process.wait()
        else:reason='NVIDIA memory measurements unavailable; manual inference uses CPU.'
        try:
            async with ollama_client(timeout=2) as client:
                response=await client.get('http://127.0.0.1:11434/api/ps');response.raise_for_status()
                for model in response.json()['models'][:20]:
                    name=model.get('name') or model.get('model');size=model.get('size_vram',0);ctx=model.get('context_length',0)
                    if not isinstance(name,str) or type(size) is not int or size<0 or type(ctx) is not int:raise ValueError()
                    resident.append(dict(model=name,size_vram_mib=size//1048576,context=ctx))
        except Exception:
            reason=reason or 'Ollama residency unavailable; resident memory is not credited.'
        return dict(gpus=gpus,resident=resident,reason=reason)


    async def unload_primary(self):
        async with ollama_client(timeout=3) as client:
            response=await client.post('http://127.0.0.1:11434/api/generate',json={'model':MODEL,'keep_alive':0,'stream':False})
            response.raise_for_status()
            payload=response.json()
            if payload.get('done') is not True or payload.get('done_reason')!='unload':
                raise RuntimeError('Ollama did not confirm model unloading')


class Resources:
    def __init__(self,notify,meeting,probe=None,settings=None):
        self.notify,self.meeting=notify,meeting;self.probe=probe or LocalProbe()
        self.settings=settings or ResourceSettings();self.measurement=dict(gpus=[],resident=[],reason='GPU measurements have not been sampled yet.')
        self.sampled=0.;self.manual_pending=False;self.owner=None;self.active_task=None;self.profile=None
        self.lock=asyncio.Lock();self.probe_lock=asyncio.Lock();self.monitor=None;self.history=[];self.low_samples=0;self.interval=2;self.last_unload=-float('inf')

    def status(self):
        return {**self.measurement,'settings':self.settings.model_dump(),'active_job':self.owner,'profile':self.profile,
                'manual_pending':self.manual_pending,'samples_age_ms':round((time.monotonic()-self.sampled)*1000) if self.sampled else None,
                'budget_is_estimate':True,'events':list(self.history)}

    def event(self,kind,detail,elapsed_ms=None):
        self.history.append(dict(kind=kind,detail=detail,elapsed_ms=elapsed_ms,at=time.time()));self.history=self.history[-20:]

    async def refresh(self):
        async with self.probe_lock:
            try:self.measurement=await self.probe.sample()
            except Exception:self.measurement=dict(gpus=[],resident=[],reason='Resource sampling failed; manual inference uses CPU.')
            self.sampled=time.monotonic()
        return self.status()

    def pressured(self):
        status=self.meeting.status()
        return status['queue_depth']>=2 or status['counts'].get('last_chunk_lag_ms',0)>5000

    def admission(self,kind):
        background=kind!='manual'
        if self.pressured():raise ResourceDeferred('Inference deferred while transcription catches up; no answer is queued.')
        if background and self.manual_pending:raise ResourceDeferred('Background analysis deferred for manual assistance.')
        gpu=self.measurement['gpus'][0] if len(self.measurement['gpus'])==1 else None
        credit=0
        if gpu:
            credit=max([min(m['size_vram_mib'],self.settings.generation_budget_mib) for m in self.measurement['resident'] if m['model']==MODEL and m['context']>=4096]+[0])
        if not self.settings.force_cpu and gpu and gpu['free_mib']+credit>=self.settings.reserve_mib+self.settings.generation_budget_mib:
            return 'gpu'
        if background:raise ResourceDeferred('Background analysis deferred: measured GPU budget/reserve is unavailable.')
        return 'cpu'

    def start(self):self.monitor=asyncio.create_task(self._monitor())

    async def _monitor(self):
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.refresh()
                low=bool(self.profile=='gpu' and (len(self.measurement['gpus'])!=1 or self.measurement['gpus'][0]['free_mib']<self.settings.reserve_mib))
                self.low_samples=self.low_samples+1 if low else 0
                if self.active_task and (self.low_samples>=2 or self.pressured()):
                    self.event('preempted','Inference cancelled to protect transcription or the measured VRAM reserve.')
                    self.active_task.cancel()
                if (not self.lock.locked() and len(self.measurement['gpus'])==1 and
                    self.measurement['gpus'][0]['free_mib']<self.settings.reserve_mib and
                    any(m['model']==MODEL for m in self.measurement['resident']) and
                    time.monotonic()-self.last_unload>10 and hasattr(self.probe,'unload_primary')):
                    async with self.lock:
                        self.last_unload=time.monotonic();await self.probe.unload_primary()
                        self.event('unloaded','Primary model residency released to restore the VRAM reserve.')
                await self.notify()
            except asyncio.CancelledError:raise
            except Exception:
                self.measurement=dict(gpus=[],resident=[],reason='Resource sampling failed; GPU admission disabled.')
                if self.active_task and self.profile=='gpu':self.active_task.cancel()

    async def begin_manual(self):
        self.manual_pending=True
        if self.active_task and self.owner!='manual':
            task=self.active_task;self.event('preempted','Background inference preempted by manual assistance.');task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    def end_manual(self):self.manual_pending=False

    @asynccontextmanager
    async def lease(self,kind):
        if kind!='manual' and (self.lock.locked() or self.manual_pending):raise ResourceDeferred('Background analysis deferred; no inference queue is created.')
        async with self.lock:
            await self.refresh();profile=self.admission(kind)
            self.owner,self.profile,self.active_task=kind,profile,asyncio.current_task();start=time.monotonic()
            token=PROFILE.set(profile);self.event('started',kind+' on '+profile)
            try:yield profile
            except asyncio.CancelledError:self.event('cancelled',kind);raise
            except Exception:self.event('failed',kind);raise
            else:self.event('completed',kind,round((time.monotonic()-start)*1000))
            finally:
                PROFILE.reset(token);self.owner=self.profile=self.active_task=None

    async def close(self):
        if self.monitor:self.monitor.cancel();await asyncio.gather(self.monitor,return_exceptions=True)
        if self.active_task and self.active_task is not asyncio.current_task():
            self.active_task.cancel();await asyncio.gather(self.active_task,return_exceptions=True)
