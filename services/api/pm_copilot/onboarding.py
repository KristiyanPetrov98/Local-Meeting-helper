"""Guided setup, explicit installations and evidence-backed device profiles."""
from .ollama_http import ollama_client
import asyncio
import hashlib
import importlib.metadata
import json
import os
import shutil
import time
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
import httpx
from .briefing import MODEL,CONTEXT
from .embeddings import MODEL as EMBEDDING_MODEL
from .meeting import AudioOptions
from .model_assets import CATALOG,recover_installations
from .resources import ResourceSettings,PROFILE
from .setup_checks import hardware,core_checks,check,worker_check,asr_silence,diarization_load
from .store import DomainError

SCHEMA='''CREATE TABLE IF NOT EXISTS setup_runs(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,completed_at TEXT,report TEXT NOT NULL);
'''

class Onboarding:
    def __init__(self,store,change,meeting,documents,assistance,screen,resources,data_dir,desktop_capability=None):
        self.store,self.change,self.meeting,self.documents,self.assistance,self.screen,self.resources=store,change,meeting,documents,assistance,screen,resources
        self.root=Path(data_dir);self.models=self.root/'models';self.models.mkdir(parents=True,exist_ok=True)
        recover_installations(self.models)
        self.legacy_whisper=self.meeting.model
        self.desktop_capability=desktop_capability;self.task=self.process=None;self.active=None;self.phase='idle';self.lock=asyncio.Lock()
        self.sleep=asyncio.sleep;self.clock=time.monotonic;self.baseline_seconds=15
        self.store.db.executescript(SCHEMA)
        with self.store.db:self.store.db.execute("UPDATE setup_runs SET status='interrupted',completed_at=? WHERE status='running'",(self.now(),))
        self.configure_paths()

    def now(self):return datetime.now(timezone.utc).isoformat()

    def preferences(self):
        result=json.loads(self.store.value('setup_preferences','{"asr_size":"medium"}'))
        result['asr_device']=AudioOptions.model_validate_json(self.store.value('audio_options',AudioOptions().model_dump_json())).device
        return result

    def configure_paths(self):
        candidate=self.models/('whisper-'+self.preferences()['asr_size'])
        self.meeting.model=candidate if candidate.is_dir() or self.preferences()['asr_size']!='medium' or getattr(__import__('sys'),'frozen',False) else self.legacy_whisper
        candidate=self.models/'community-1'
        if candidate.is_dir() or getattr(__import__('sys'),'frozen',False):self.meeting.diar_model=candidate

    def summary(self):return dict(completed=bool(self.store.value('setup_acknowledged')),active_run_id=self.active,phase=self.phase,busy=bool(self.active))

    def run(self,id):
        row=self.store.db.execute('SELECT * FROM setup_runs WHERE id=?',(id,)).fetchone()
        if not row:raise DomainError('Setup run not found',404)
        return {**dict(row),'report':json.loads(row['report'])}

    def status(self):
        recent=[self.run(r['id']) for r in self.store.db.execute('SELECT id FROM setup_runs ORDER BY created_at DESC LIMIT 10')]
        assets=[]
        for id,value in CATALOG.items():
            assets.append(dict(id=id,**value,files_present=(self.models/id).is_dir() if value['kind']=='snapshot' else None,inference_verified=False))
        return dict(**self.summary(),preferences=self.preferences(),acknowledgement=json.loads(self.store.value('setup_acknowledged','null')),assets=assets,runs=recent,selected_profile=json.loads(self.store.value('selected_device_profile','null')))

    def require_idle(self):
        if self.store.live():raise DomainError('Stop the meeting before installation or offline setup checks')
        if self.assistance.active:raise DomainError('Wait for manual assistance to finish')

    async def diagnostics(self):
        result=hardware(self.root);result['resources']=await self.resources.refresh()
        result['audio']=self.meeting.diagnostics();result['screen']=self.screen.native.diagnostics()
        packages={}
        for name in ('faster-whisper','ctranslate2','onnxruntime','pyannote.audio','torch','langdetect','pypdf'):
            try:packages[name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:packages[name]=None
        result['packages']=packages
        try:
            async with ollama_client(timeout=3) as client:
                response=await client.get('http://127.0.0.1:11434/api/tags');response.raise_for_status()
                result['ollama']={'reachable':True,'models':[{'name':m.get('name'),'digest':m.get('digest')} for m in response.json().get('models',[])[:50]]}
        except Exception:result['ollama']={'reachable':False,'models':[]}
        result['generation_model']=MODEL;result['embedding_model']=EMBEDDING_MODEL
        result['qualification']='Measurements and library presence do not establish inference, audio or Windows capture success.'
        return result

    async def configure(self,config):
        self.require_idle()
        if self.active:raise DomainError('Finish the active setup operation first')
        audio=AudioOptions.model_validate_json(self.store.value('audio_options',AudioOptions().model_dump_json()))
        audio.device=config.asr_device
        resources=ResourceSettings(reserve_mib=config.reserve_mib,generation_budget_mib=config.generation_budget_mib,force_cpu=config.force_cpu)
        def save():
            self.store.setting('setup_preferences',json.dumps({'asr_size':config.asr_size}))
            self.store.setting('audio_options',audio.model_dump_json())
            self.store.setting('resource_settings',resources.model_dump_json())
            self.store.setting('selected_device_profile','null');self.store.bump()
        self.resources.settings=resources;await self.change(save);self.configure_paths()
        return self.status()

    async def start(self,kind,params=None):
        params=params or {}
        async with self.lock:
            if self.active:raise DomainError('One setup operation may run at a time; there is no installation queue')
            if kind=='benchmark':
                live=self.store.live()
                if not live or live['state']!='active' or self.meeting.state!='capturing':raise DomainError('Start a consented session with real audio capture before benchmarking')
                if self.assistance.active:raise DomainError('Wait for manual assistance before benchmarking')
            else:self.require_idle()
            if kind in ('download','import') and CATALOG[params['model_id']]['kind']=='snapshot' and (self.models/params['model_id']).exists() and not params.get('replace'):
                raise DomainError('Snapshot already exists; verify it or explicitly select replacement',409)
            rid=str(uuid4());self.active=rid;self.phase=kind
            def save():
                self.store.db.execute('INSERT INTO setup_runs VALUES(?,?,?,?,?,?)',(rid,kind,'running',self.now(),None,json.dumps({'phase':kind,'model_id':params.get('model_id')})))
                self.store.bump()
            await self.change(save);self.task=asyncio.create_task(self._execute(rid,kind,params))
            return self.run(rid)

    async def _finish(self,rid,status,report):
        def save():
            self.store.db.execute('UPDATE setup_runs SET status=?,completed_at=?,report=? WHERE id=?',(status,self.now(),json.dumps(report),rid));self.store.bump()
        await self.change(save)

    async def _execute(self,rid,kind,params):
        self.documents.manual_active=True
        temporary=self.models/'.downloads'/rid
        try:
            if kind=='self_test':
                async with asyncio.timeout(300):report=await self.self_tests()
            elif kind=='benchmark':
                async with asyncio.timeout(300):report=await self.benchmark()
            else:
                async with asyncio.timeout(3600):report=await self.install(kind,params,temporary)
            await self._finish(rid,'completed',report)
        except asyncio.CancelledError:
            await self._finish(rid,'cancelled',dict(detail='Setup operation cancelled; no qualification was recorded.'));raise
        except Exception:
            await self._finish(rid,'failed',dict(detail='Setup operation failed or timed out. Check dependencies, model access, free disk space and runtime status; no qualification was recorded.'))
        finally:
            if self.process and self.process.returncode is None:self.process.kill();await self.process.wait()
            self.process=None
            if temporary.exists():await asyncio.to_thread(shutil.rmtree,temporary)
            if self.active==rid:
                self.active=None;self.phase='idle';self.documents.manual_active=False
                await self.change(self.store.bump)

    async def install(self,kind,params,temporary):
        model_id=params['model_id'];model=CATALOG[model_id]
        if model['kind']=='ollama':
            if not params.get('replace'):
                try:existing=await (self.assistance.generator.identity() if model_id=='generation' else self.documents.embedder.identity(refresh=True))
                except Exception:existing=None
                if existing:return dict(model_id=model_id,digest=existing,files_installed=True,already_present=True,inference_verified=False,license_acknowledged=True,detail='Exact model already installed; no pull was needed. Run offline inference checks next.')
            async with ollama_client(timeout=httpx.Timeout(120,read=120)) as client:
                async with client.stream('POST','http://127.0.0.1:11434/api/pull',json={'model':model['name'],'stream':True}) as response:
                    response.raise_for_status();success=False
                    async for line in response.aiter_lines():
                        if not line:continue
                        event=json.loads(line)
                        if event.get('error'):raise ValueError('Pull rejected')
                        if event.get('status')=='success':success=True
                    if not success:raise ValueError('Pull did not complete')
            identity=await (self.assistance.generator.identity() if model_id=='generation' else self.documents.embedder.identity(refresh=True))
            return dict(model_id=model_id,digest=identity,license_acknowledged=True,files_installed=True,inference_verified=False,detail='Local Ollama confirmed the exact model. Run offline inference checks next.')
        temporary.mkdir(parents=True,exist_ok=True)
        cfg=dict(action=kind,model_id=model_id,destination=str(self.models/model_id),temporary_root=str(temporary),replace=params.get('replace',False))
        if params.get('source'):cfg['source']=params['source']
        if params.get('access_token'):cfg['access_token']=params['access_token']
        result=await worker_check(self,'assets',cfg,3500)
        if result.get('type')!='installed':raise ValueError('Installation failed')
        self.configure_paths()
        return dict(model_id=model_id,files_installed=True,inference_verified=False,revision=result['result'].get('revision'),provenance=result['result'].get('provenance'),detail='Snapshot structure and local checksums recorded. Inference and accuracy remain untested.')

    async def self_tests(self):
        rows=await asyncio.to_thread(core_checks,self.root)
        try:
            data=await worker_check(self,'document',{'name':'offline.txt','content':__import__('base64').b64encode(b'Offline parser child process').decode()},45)
            assert data['type']=='parsed' and data['result']['chunks']
            rows.append(check('parser_worker','Bundled parser process','passed','Private child process parsed a synthetic document and exited.'))
        except Exception:rows.append(check('parser_worker','Bundled parser process','failed','The isolated document worker could not complete.'))
        try:
            result=await worker_check(self,'checks',{'modules':['faster_whisper','ctranslate2','onnxruntime','pyannote.audio']},90)
            for module,state in result['results'].items():rows.append(check('import_'+module,module+' runtime',state,'Actual isolated import result; this is not a model-quality test.'))
        except Exception:rows.append(check('runtime_imports','Supporting runtime imports','failed','The isolated runtime check could not finish.'))
        try:
            await self.resources.begin_manual()
            try:
                async with self.resources.lease('manual'):
                    before=await self.assistance.generator.identity()
                    content,metrics=await self.assistance.generator.generate([dict(role='system',content='Return only the supplied JSON schema.'),dict(role='user',content='Return the integer result of 2 + 2 as value.')],{'type':'object','properties':{'value':{'type':'integer'}},'required':['value'],'additionalProperties':False})
                    assert json.loads(content)=={'value':4} and await self.assistance.generator.identity()==before
            finally:self.resources.end_manual()
            rows.append(check('generation','Offline local generation','passed','Actual primary-model inference through fixed loopback endpoint returned the expected result.',metrics))
        except Exception:rows.append(check('generation','Offline local generation','blocked','The exact primary Ollama model/runtime could not pass the local inference check.'))
        try:
            async with self.documents.embed_lock:
                identity=await self.documents.embedder.identity();vectors=await self.documents.embedder.embed(['Offline retrieval test'],query=True)
                assert len(vectors)==1 and len(vectors[0])>0 and await self.documents.embedder.identity(refresh=True)==identity
            rows.append(check('embedding','Offline local embeddings','passed','Actual CPU embedding inference returned a valid vector.'))
        except Exception:rows.append(check('embedding','Offline local embeddings','blocked','The exact local embedding runtime/model could not complete inference.'))
        if self.meeting.model.is_dir():
            try:
                await asr_silence(self,self.meeting)
                rows.append(check('asr_runtime','Offline Whisper model load','passed','Actual CPU model load and one second of synthetic silence completed. This does not verify speech accuracy.'))
            except Exception:rows.append(check('asr_runtime','Offline Whisper model load','blocked','Local Whisper model loading/silence inference failed.'))
        else:rows.append(check('asr_runtime','Offline Whisper model load','blocked','Install or import the approved local Whisper snapshot first.'))
        if self.meeting.diar_model.is_dir():
            try:
                await diarization_load(self,self.meeting)
                rows.append(check('diarization_runtime','Offline Community-1 model load','passed','The actual CPU diarization worker loaded its local pipeline. Speaker accuracy still requires live review.'))
            except Exception:rows.append(check('diarization_runtime','Offline Community-1 model load','blocked','The local diarization pipeline did not load.'))
        else:rows.append(check('diarization_runtime','Offline Community-1 model load','blocked','Install the complete approved offline Community-1 snapshot.'))
        for id,label,operation,available in [('audio_enumeration','Windows audio device enumeration',self.meeting.enumerate_devices,self.meeting.diagnostics()['available']),('window_enumeration','Windows selected-window enumeration',self.screen.native.windows,self.screen.native.diagnostics()['available'])]:
            if not available:rows.append(check(id,label,'blocked','Required Windows helper/runtime unavailable.'))
            else:
                try:await operation();rows.append(check(id,label,'passed','Actual helper enumeration completed; capture still needs a consented live check.'))
                except Exception:rows.append(check(id,label,'failed','The installed native helper could not enumerate.'))
        rows.append(check('endpoint_policy','Local inference endpoint policy','passed','Inference clients use fixed 127.0.0.1 endpoints; offline workers disable Hub access. OS-wide network isolation was not asserted.'))
        return dict(checks=rows,fingerprint=self.fingerprint(),all_passed=all(r['status']=='passed' for r in rows),scope='Offline runtime checks; live bilingual speech, Meet audio, selected-window capture and sustained workload remain separate.')

    def live_check(self):
        live=self.store.live()
        if not live:return dict(available=False,detail='Start a consented live test session; capture is never started by diagnostics.')
        status=self.meeting.status();languages={r['language']:r['count'] for r in self.store.db.execute('SELECT language,COUNT(*) AS count FROM transcript_segments WHERE session_id=? GROUP BY language',(live['id'],))}
        return dict(available=True,project_id=live['project_id'],session_id=live['id'],state=live['state'],audio_state=status['state'],counts=status['counts'],queue_depth=status['queue_depth'],languages=languages,
                    screen_frames=self.screen.counts.get('frames',0) if self.screen.sid==live['id'] else 0,screen_preview_available=self.screen.status()['preview_available'],capture_exclusion_verified=False,
                    detail='Energy, transcript languages and captured frames are observations; inspect accuracy and Meet sharing in the actual preview.')

    def fingerprint(self):
        gpu=[{key:g[key] for key in ('uuid','name','total_mib')} for g in self.resources.measurement['gpus']]
        model=self.meeting.model/'installation.json'
        manifest=hashlib.sha256(model.read_bytes()).hexdigest() if model.is_file() else None
        data=dict(preferences=self.preferences(),audio=json.loads(self.store.value('audio_options',AudioOptions().model_dump_json())),resource_settings=self.resources.settings.model_dump(),gpus=gpu,asr_manifest=manifest)
        return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

    async def benchmark(self):
        live=self.store.live();sid=live['id'];started_at=self.now();start=self.clock();before=dict(self.meeting.status()['counts']);samples=[];minimum_free=None;memory_samples=[]
        async def sample_memory():
            previous=None
            while True:
                if self.resources.sampled!=previous and len(self.resources.measurement['gpus'])==1:
                    previous=self.resources.sampled;gpu=self.resources.measurement['gpus'][0]
                    memory_samples.append(dict(elapsed_ms=round((self.clock()-start)*1000),total_mib=gpu['total_mib'],free_mib=gpu['free_mib']))
                await asyncio.sleep(.5)
        sampler=None
        try:
            await self.resources.begin_manual()
            sampler=asyncio.create_task(sample_memory())
            await self.sleep(self.baseline_seconds)
            identity=await self.assistance.generator.identity()
            for _ in range(3):
                begin=self.clock()
                async with self.resources.lease('manual') as profile:
                    content,metrics=await self.assistance.generator.generate([dict(role='system',content='Return only schema JSON. Write factual English, without personal or company information.'),dict(role='user',content='Write a neutral 120 to 180 word explanation of idempotency and safe request retries. Synthetic workload context: '+('A bounded local integration benchmark. '*35))],{'type':'object','properties':{'summary':{'type':'string','minLength':450,'maxLength':1400}},'required':['summary'],'additionalProperties':False})
                    value=json.loads(content)
                    if not isinstance(value.get('summary'),str) or not 450<=len(value['summary'])<=1400:raise ValueError('Incomplete benchmark generation')
                if await self.assistance.generator.identity()!=identity:raise ValueError('Model changed')
                await self.resources.refresh()
                free=self.resources.measurement['gpus'][0]['free_mib'] if len(self.resources.measurement['gpus'])==1 else None
                if free is not None:minimum_free=free if minimum_free is None else min(minimum_free,free)
                samples.append(dict(elapsed_ms=round((self.clock()-begin)*1000),profile=profile,metrics=metrics,synthetic_summary=value['summary']))
            after=dict(self.meeting.status()['counts']);live_now=self.store.live()
            languages={r['language'] for r in self.store.db.execute('SELECT DISTINCT language FROM transcript_segments WHERE session_id=? AND created_at>=?',(sid,started_at))}
            elapsed=self.clock()-start
            if memory_samples:minimum_free=min([s['free_mib'] for s in memory_samples]+([minimum_free] if minimum_free is not None else []))
            errors=sum(max(0,after.get(key,0)-before.get(key,0)) for key in ('gaps','dropped_chunks','asr_errors','native_dropped_packets'))
            passed=bool(live_now and live_now['id']==sid and live_now['state']=='active' and self.meeting.state=='capturing' and
                after.get('packets',0)>before.get('packets',0) and after.get('segments',0)>before.get('segments',0) and
                after.get('local_audible_packets',0)>0 and after.get('remote_audible_packets',0)>0 and {'en','bg'}<=languages and errors==0 and
                after.get('last_chunk_lag_ms',999999)<=5000 and all(s['elapsed_ms']<=60000 for s in samples) and elapsed>=self.baseline_seconds and
                len({s['profile'] for s in samples})==1 and (samples[0]['profile']=='cpu' or minimum_free is not None and minimum_free>=self.resources.settings.reserve_mib))
            return dict(short_check_passed=passed,samples=samples,elapsed_ms=round(elapsed*1000),asr_counts_before=before,asr_counts_after=after,languages_observed=sorted(languages),errors_added=errors,
                minimum_observed_free_mib=minimum_free,gpu_memory_samples=memory_samples,peak_observed_used_mib=max((s['total_mib']-s['free_mib'] for s in memory_samples),default=None),model=MODEL,model_digest=identity,context=CONTEXT,asr_device=getattr(self.meeting,'asr_device','cpu'),fingerprint=self.fingerprint(),
                scope='Short synthetic generation with live bilingual ASR; human accuracy review and 90-minute release qualification are still required.')
        finally:
            if sampler:
                sampler.cancel();await asyncio.gather(sampler,return_exceptions=True)
            self.resources.end_manual()

    async def apply_profile(self,rid,accuracy_ack):
        self.require_idle()
        if self.active:raise DomainError('Finish the active setup operation first')
        report=self.run(rid)['report']
        await self.resources.refresh()
        if not accuracy_ack or not report.get('short_check_passed') or report.get('fingerprint')!=self.fingerprint():
            raise DomainError('A matching successful short benchmark and explicit speech/output accuracy review are required',422)
        try:identity=await self.assistance.generator.identity()
        except Exception:raise DomainError('The local model identity is unavailable; restart Ollama and repeat the checks',422)
        if identity!=report.get('model_digest'):raise DomainError('The generation model changed; repeat the benchmark',422)
        audio=AudioOptions.model_validate_json(self.store.value('audio_options',AudioOptions().model_dump_json()));audio.device=report['asr_device']
        self.resources.settings.force_cpu=report['samples'][0]['profile']=='cpu'
        def save():
            self.store.setting('audio_options',audio.model_dump_json());self.store.setting('resource_settings',self.resources.settings.model_dump_json())
            self.store.setting('selected_device_profile',json.dumps({'run_id':rid,'fingerprint':self.fingerprint(),'model_digest':report['model_digest'],'accuracy_review_acknowledged':True,'qualification':'short device check only; M7 release qualification pending'}));self.store.bump()
        await self.change(save)
        return self.status()

    async def acknowledge(self,privacy,sharing,allow_incomplete):
        if self.active:raise DomainError('Finish or cancel the active setup operation first')
        if not privacy or not sharing:raise DomainError('Acknowledge local data retention and sharing limitations',422)
        runs=[r for r in self.status()['runs'] if r['kind']=='self_test' and r['status']=='completed']
        profile=json.loads(self.store.value('selected_device_profile','null'))
        ready=bool(runs and runs[0]['report'].get('all_passed') and runs[0]['report'].get('fingerprint')==self.fingerprint() and profile and profile.get('fingerprint')==self.fingerprint())
        if ready:
            try:ready=await self.assistance.generator.identity()==profile.get('model_digest')
            except Exception:ready=False
        if not ready and not allow_incomplete:raise DomainError('Required checks are incomplete; explicitly continue in limited mode or finish testing',422)
        def save():
            self.store.setting('setup_acknowledged',json.dumps(dict(at=self.now(),limited=not ready,privacy_acknowledged=True,sharing_acknowledged=True,release_qualified=False)));self.store.bump()
        await self.change(save)
        return self.status()

    async def cancel(self):
        rid=self.active
        if self.task and rid:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
            if self.run(rid)['status']=='running':await self._finish(rid,'cancelled',dict(detail='Setup cancelled before its worker started.'))
            self.active=None;self.phase='idle';self.documents.manual_active=False;await self.change(self.store.bump)
        return self.status()

    async def interrupt_benchmark(self):
        if self.active and self.run(self.active)['kind']=='benchmark':await self.cancel()

    async def close(self):await self.cancel()
