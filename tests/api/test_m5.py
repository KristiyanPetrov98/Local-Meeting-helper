"""M5 portable fixtures verify orchestration; no Windows/GPU/model qualification."""
import asyncio
import base64
import io
import json
import time
from types import SimpleNamespace
from datetime import datetime,timezone
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from conftest import NoHardwareMeeting,NoModelEmbeddings
from pm_copilot.app import create_app
from pm_copilot.briefing import MODEL,BriefingInvalid,build_prompt
from pm_copilot.questions import Question
from pm_copilot.generation import OllamaGeneration
from pm_copilot.resources import Resources,LocalProbe,ResourceDeferred,ResourceSettings,PROFILE
from pm_copilot.visual import Changes,decode_frame,validate_observation,analysis_prompt
from test_assistance import FixtureGeneration,payload,trigger,finished
from test_app import project


def frame(color='white',sequence=0,source_id='123:456'):
    buffer=io.BytesIO();Image.new('RGB',(64,48),color).save(buffer,format='PNG')
    return dict(type='frame',source_id=source_id,sequence=sequence,png=base64.b64encode(buffer.getvalue()).decode())


class Probe:
    def __init__(self,free=11264,resident=0):self.free=free;self.resident=resident;self.unloads=0
    async def sample(self):return dict(gpus=[dict(uuid='GPU-fixture',name='Portable fixture GPU',total_mib=12288,free_mib=self.free)],resident=[dict(model=MODEL,size_vram_mib=self.resident,context=4096)] if self.resident else [],reason=None)
    async def unload_primary(self):self.unloads+=1;self.resident=0;self.free=11264


class Native:
    process=None
    def __init__(self):self.color='white';self.closed=False;self.broken=False
    def diagnostics(self):return dict(available=True,reason=None)
    async def windows(self):return [dict(id='123:456',hwnd=123,pid=456,title='Explicit test window')]
    async def frames(self,source):
        i=0
        while True:
            if self.broken:raise RuntimeError('Fixture capture failure')
            yield frame(self.color,i,source);i+=1;await asyncio.sleep(.02)
    async def close(self):self.closed=True


class Observer(FixtureGeneration):
    def __init__(self):super().__init__();self.observations=0;self.delay=0;self.output=None;self.image=None
    async def observe(self,messages,schema,image=None):
        self.observations+=1;self.image=image;self.messages=messages;await asyncio.sleep(self.delay)
        return json.dumps(self.output or {'observation':'The selected application window contains a plain white test area.' if image else None,'risks':[]}),dict(prompt_eval_count=700,eval_count=60)


@pytest.fixture
def m5(tmp_path):
    native,probe,observer,generator=Native(),Probe(),Observer(),FixtureGeneration()
    app=create_app(tmp_path/'m5.sqlite3','test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=NoModelEmbeddings,resource_probe=probe,screen_native_factory=lambda:native,observation_factory=lambda:observer,generation_factory=lambda:generator)
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:yield c,native,probe,observer,generator


def start(c,screen=True,risks=True):
    p=project(c,'M5 Alpha');c.post(f'/api/projects/{p}/select')
    assert c.put('/api/sharing',json={'mode':'tab','acknowledged':True}).status_code==200
    if screen:assert c.put(f'/api/projects/{p}/screen',json={'source_id':'123:456'}).status_code==200
    r=c.post('/api/sessions',json=dict(consent=True,project_id=p,screen=screen,risks=risks));assert r.status_code==201,r.text
    return p,r.json()['session']['id']


def wait_until(check,timeout=3):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if check():return
        time.sleep(.01)
    pytest.fail('Fixture condition did not become true')


def test_real_png_decode_and_change_stability_rate_limit():
    png,jpeg,signature=decode_frame(frame())
    assert png.startswith(b'\x89PNG') and jpeg.startswith(b'\xff\xd8') and len(signature)==576
    changes=Changes();assert not changes.update(signature,0) and not changes.ready(1.49)
    assert changes.update(signature,1.5);changes.attempted(1.5);changes.accepted(signature)
    dark=decode_frame(frame('black'))[2]
    assert not changes.update(dark,2) and not changes.ready(3.5)
    assert changes.ready(11.5)
    changes.accepted(dark);assert not changes.ready(30)


@pytest.mark.parametrize('event',[{'sequence':0,'png':'bad'},{'sequence':-1,'png':''},{'sequence':0,'png':'x'*5600001}])
def test_invalid_or_oversized_frames_are_rejected(event):
    with pytest.raises(ValueError):decode_frame(event)


@pytest.mark.parametrize('free,resident,expected',[(11264,0,'gpu'),(3072,8192,'gpu'),(2048,0,'cpu')])
def test_measured_memory_and_residency_control_admission(free,resident,expected):
    async def check():
        async def notify():pass
        meeting=SimpleNamespace(status=lambda:dict(queue_depth=0,counts={}))
        resources=Resources(notify,meeting,Probe(free,resident));await resources.refresh()
        assert resources.admission('manual')==expected
        if expected=='cpu':
            with pytest.raises(ResourceDeferred):resources.admission('vision')
    asyncio.run(check())


def test_manual_preempts_background_without_queuing_and_keeps_transcript_worker_free():
    async def check():
        async def notify():pass
        meeting=SimpleNamespace(status=lambda:dict(queue_depth=0,counts={}),stopped=False)
        r=Resources(notify,meeting,Probe());entered=asyncio.Event()
        async def background():
            async with r.lease('vision'):
                entered.set();await asyncio.sleep(30)
        task=asyncio.create_task(background());await entered.wait()
        with pytest.raises(ResourceDeferred):
            async with r.lease('risk'):pass
        await r.begin_manual();assert task.cancelled() and not meeting.stopped
        async with r.lease('manual') as profile:assert PROFILE.get()==profile=='gpu'
        r.end_manual();assert not r.lock.locked() and r.owner is None
    asyncio.run(check())


def test_asr_pressure_defers_background_and_missing_gpu_uses_bounded_cpu():
    async def check():
        async def notify():pass
        class Missing:
            async def sample(self):raise RuntimeError('Fixture telemetry failure')
        meeting=SimpleNamespace(status=lambda:dict(queue_depth=3,counts={}))
        r=Resources(notify,meeting,Missing())
        await r.refresh()
        with pytest.raises(ResourceDeferred):r.admission('manual')
        with pytest.raises(ResourceDeferred):r.admission('risk')
        meeting.status=lambda:dict(queue_depth=0,counts={})
        r.settings=ResourceSettings(force_cpu=True)
        async with r.lease('manual'):assert PROFILE.get()=='cpu'
    asyncio.run(check())


@pytest.mark.parametrize('missing',[False,True])
def test_memory_pressure_cancels_optional_work_and_unloads_only_owned_primary(missing):
    async def check():
        async def notify():pass
        probe=Probe();r=Resources(notify,SimpleNamespace(status=lambda:dict(queue_depth=0,counts={})),probe);r.interval=.01
        entered=asyncio.Event()
        async def job():
            async with r.lease('vision'):entered.set();await asyncio.sleep(30)
        task=asyncio.create_task(job());await entered.wait();probe.free=512;probe.resident=8192
        if missing:
            async def no_measurements():return dict(gpus=[],resident=[],reason='Fixture telemetry unavailable')
            probe.sample=no_measurements
        r.start()
        await asyncio.wait_for(asyncio.gather(task,return_exceptions=True),1)
        if not missing:
            for _ in range(100):
                if probe.unloads:break
                await asyncio.sleep(.01)
        assert task.cancelled() and probe.unloads==(0 if missing else 1)
        await r.close()
    asyncio.run(check())


def test_capture_preview_scopes_and_pause_stop_clear_all_ephemeral_data(m5):
    c,native,probe,observer,gen=m5;p,s=start(c)
    wait_until(lambda:c.get('/api/screen').json()['preview_available'])
    route=f'/api/projects/{p}/sessions/{s}/screen/preview';preview=c.get(route)
    assert preview.headers['content-type']=='image/png' and preview.headers['cache-control']=='no-store'
    assert preview.content.startswith(b'\x89PNG')
    other=project(c,'M5 Beta');assert c.get(f'/api/projects/{other}/sessions/{s}/screen/preview').status_code==404
    assert c.put(f'/api/projects/{p}/screen',json={'source_id':None}).status_code==409
    c.post(f'/api/sessions/{s}/pause');assert c.get(route).status_code==404
    assert c.app.state.screen.observation is None and not c.app.state.screen.risks
    c.post(f'/api/sessions/{s}/resume');wait_until(lambda:c.get('/api/screen').json()['preview_available'])
    c.post(f'/api/sessions/{s}/stop');assert c.get(route).status_code==404 and native.closed
    assert c.get('/api/state').json()['session']['state']=='stopped'
    assert not list(c.app.state.store.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%screen%'"))


def test_actual_debounce_analysis_is_once_for_unchanged_scene_and_context_is_project_scoped(m5):
    c,native,probe,observer,gen=m5;p,s=start(c)
    wait_until(lambda:c.get('/api/screen').json()['observation_available'],4)
    assert observer.observations==1 and observer.image.startswith(b'\xff\xd8')
    screen=c.app.state.screen
    assert screen.context(p,s) and screen.context('other',s) is None
    native.color='black';wait_until(lambda:screen.observation is None)
    assert observer.observations==1 # 10-second rate limit still applies.
    assert gen.calls==0 and c.app.state.store.db.execute('SELECT count(*) FROM generated_responses').fetchone()[0]==0


def test_capture_failure_preserves_session_and_transcript_ingestion(m5):
    c,native,probe,observer,gen=m5;p,s=start(c);native.broken=True
    wait_until(lambda:c.get('/api/screen').json()['state']=='error')
    store=c.app.state.store;store.add_segment(s,'remote',0,2,'A confirmed sentence during capture failure.','en','failure')
    assert c.get('/api/state').json()['session']['state']=='active'
    assert c.get(f'/api/projects/{p}/sessions/{s}/transcript').json()['segments']
    assert c.app.state.screen.frame is None and c.app.state.screen.observation is None


@pytest.mark.parametrize('mode',['unknown','broader'])
def test_sharing_guards_clear_capture_and_cannot_claim_verified_exclusion(m5,mode):
    c,native,probe,observer,gen=m5;p,s=start(c)
    result=c.put('/api/sharing',json=dict(mode=mode,acknowledged=True,preview_confirmed=True)).json()
    assert not result['mini_allowed'] and not result['capture_exclusion_verified'] and not result['meet_picker_enforced']
    assert c.get('/api/state').json()['session']['state']=='active'
    assert c.app.state.screen.frame is None
    assert c.put('/api/sharing',json={'mode':'tab','acknowledged':False}).status_code==422
    assert c.put('/api/sharing',json={'mode':'tab','acknowledged':True,'capture_exclusion_verified':True}).status_code==422


def test_window_selection_rejects_unknown_handles_and_is_cleared_on_project_change(m5):
    c,native,probe,observer,gen=m5;p=project(c,'Window Alpha');c.post(f'/api/projects/{p}/select')
    assert c.put(f'/api/projects/{p}/screen',json={'source_id':'999:999'}).status_code==404
    assert c.put(f'/api/projects/{p}/screen',json={'source_id':'123:456'}).status_code==200
    other=project(c,'Window Beta');c.post(f'/api/projects/{other}/select')
    assert c.get('/api/screen').json()['selected'] is None
    assert c.post('/api/sessions',json=dict(consent=True,project_id=other,screen=True)).status_code==422
    assert c.get('/api/screen/windows',headers={'Authorization':''}).status_code==401


def test_resource_settings_validate_and_persist_and_cpu_manual_keeps_primary_model(m5):
    c,native,probe,observer,gen=m5
    assert c.put('/api/resources/settings',json={'reserve_mib':0}).status_code==422
    assert c.put('/api/resources/settings',json={'reserve_mib':3072,'generation_budget_mib':8192,'force_cpu':True}).status_code==200
    assert json.loads(c.app.state.store.value('resource_settings'))['reserve_mib']==3072
    p,s=start(c,False,False);store=c.app.state.store
    store.add_segment(s,'remote',0,2,'How can retries avoid duplicates?','en','question')
    c.app.state.assistance.clock=lambda:datetime.fromisoformat(store.require_session(p,s)['started_at']).timestamp()+3
    base=f'/api/projects/{p}/sessions/{s}/assistance';rid=trigger(c,base).json()['id']
    detail=finished(c,base,rid,'completed')
    assert any('CPU' in w for w in detail['warnings']) and detail['response']['model']==MODEL


def test_recent_screen_context_is_frozen_for_manual_prompt_and_never_becomes_a_document_citation(m5):
    c,native,probe,observer,gen=m5;p,s=start(c,True,False)
    wait_until(lambda:c.get('/api/screen').json()['observation_available'],4)
    store=c.app.state.store;store.add_segment(s,'remote',0,2,'How can retries avoid duplicates?','en','q')
    c.app.state.assistance.clock=lambda:datetime.fromisoformat(store.require_session(p,s)['started_at']).timestamp()+3
    base=f'/api/projects/{p}/sessions/{s}/assistance';rid=trigger(c,base).json()['id'];result=finished(c,base,rid,'completed')
    data=json.loads(gen.messages[1]['content'])
    assert 'plain white' in data['screen_observation_unverified'] and result['citations']==[]
    assert result['response']['metrics']['input_bytes_including_schema']<=3072


def test_audio_only_risk_analysis_is_ephemeral_with_inspectable_evidence(m5):
    c,native,probe,observer,gen=m5;p,s=start(c,False,True);store=c.app.state.store
    store.add_segment(s,'remote',0,.1,'The required database driver is still missing.','en','risk')
    seg=store.transcript(p,s)['segments'][0]
    observer.output={'observation':None,'risks':[dict(kind='missing_dependency',text='The missing database driver may block the integration work.',citation_ids=[],segment_ids=[seg['id']],screen_evidence=False)]}
    wait_until(lambda:c.get('/api/screen').json()['risk_count']==1,4)
    hint=c.get('/api/screen').json()['risks'][0]
    assert hint['segments'][0]['text']==seg['text'] and gen.calls==0
    assert store.db.execute('SELECT count(*) FROM generated_responses').fetchone()[0]==0
    c.post(f'/api/sessions/{s}/stop');assert c.get('/api/screen').json()['risks']==[]


@pytest.mark.parametrize('change',['foreign_citation','foreign_segment','invented_screen','no_evidence','contradiction','script','language','extra_answer'])
def test_risk_validation_rejects_unverifiable_or_answer_like_output(change):
    value={'observation':None,'risks':[dict(kind='missing_dependency',text='The missing dependency may delay implementation.',citation_ids=[],segment_ids=[1],screen_evidence=False)]}
    risk=value['risks'][0]
    if change=='foreign_citation':risk['citation_ids']=['foreign']
    if change=='foreign_segment':risk['segment_ids']=[999]
    if change=='invented_screen':risk['screen_evidence']=True
    if change=='no_evidence':risk['segment_ids']=[]
    if change=='contradiction':risk['kind']='document_contradiction'
    if change=='script':risk['text']='We should tell the team that this problem is solved.'
    if change=='language':risk['text']='Липсващата зависимост може да забави изпълнението.'
    if change=='extra_answer':value['meeting_answer']='An unsolicited answer'
    with pytest.raises(BriefingInvalid):validate_observation(json.dumps(value),[{'id':1}],[],False)


def test_ollama_cpu_and_visual_protocol_keep_images_in_memory(monkeypatch):
    original=httpx.AsyncClient;calls=[]
    def handle(request):
        body=json.loads(request.content);calls.append(body)
        assert request.url.host=='127.0.0.1' and body['model']==MODEL and body['options']['num_ctx']==4096
        if len(calls)==1:
            assert body['options']['num_gpu']==0 and body['options']['num_thread']==4 and body['keep_alive']==0
        else:
            assert body['options']['num_predict']==384 and body['messages'][0]['role']=='system'
            assert base64.b64decode(body['messages'][1]['images'][0])==b'fixture image bytes'
        return httpx.Response(200,json=dict(done=True,message=dict(role='assistant',content='{}'),prompt_eval_count=700,eval_count=20))
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    async def check():
        token=PROFILE.set('cpu')
        try:await OllamaGeneration().generate([],{} )
        finally:PROFILE.reset(token)
        await OllamaGeneration().observe([dict(role='system',content='system'),dict(role='user',content='data')],{},b'fixture image bytes')
    asyncio.run(check());assert len(calls)==2


@pytest.mark.parametrize('mutation',['delete','revision','transcript','expire'])
def test_risk_evidence_is_revalidated_and_expired_before_display(m5,mutation):
    from pm_copilot.document_parser import parse_document
    c,native,probe,observer,gen=m5;p,s=start(c,False,False);store=c.app.state.store;screen=c.app.state.screen
    body=b'The release is scheduled for Friday.'
    doc=store.upload_document(p,'release.txt',body);store.commit_parsed(p,doc['document_id'],doc['revision_id'],parse_document('release.txt',body))
    store.add_segment(s,'remote',0,.1,'The release deadline is Monday.','en','risk-evidence')
    row=dict(store.db.execute('SELECT * FROM transcript_segments WHERE session_id=?',(s,)).fetchone())
    cid=store.lexical_candidates(p,'release')[0]['id'];screen.risks_enabled=True
    observer.output={'observation':None,'risks':[dict(kind='document_contradiction',text='The stated deadline may conflict with the documented release date.',citation_ids=[cid],segment_ids=[row['id']],screen_evidence=False)]}
    c.portal.call(screen.analyze,None,[row],'digest')
    assert screen.status()['risk_count']==1
    if mutation=='delete':store.delete_document(p,doc['document_id'])
    elif mutation=='revision':store.upload_document(p,'release.txt',b'The release date has changed.')
    elif mutation=='transcript':
        with store.db:store.db.execute('DELETE FROM transcript_segments WHERE id=?',(row['id'],))
    else:
        now=screen.clock();screen.clock=lambda:now+91
    assert screen.status()['risk_count']==0


@pytest.mark.parametrize('bad',['source','sequence'])
def test_wrong_source_or_repeated_frame_sequence_fails_closed(m5,bad):
    c,native,probe,observer,gen=m5
    async def malformed(source):
        yield frame(sequence=0,source_id=source)
        yield frame(sequence=0 if bad=='sequence' else 1,source_id='wrong-source' if bad=='source' else source)
    native.frames=malformed
    p,s=start(c);wait_until(lambda:c.get('/api/screen').json()['state']=='error')
    assert c.app.state.screen.frame is None and c.get('/api/state').json()['session']['state']=='active'


def test_low_gpu_memory_defers_background_analysis_without_calling_model(m5):
    c,native,probe,observer,gen=m5;probe.free=1024;p,s=start(c,False,True)
    c.app.state.store.add_segment(s,'remote',0,.1,'A required library is missing.','en','pressure')
    wait_until(lambda:'deferred' in (c.get('/api/screen').json()['error'] or ''),3)
    assert observer.observations==gen.calls==0 and c.get('/api/state').json()['session']['state']=='active'


def test_visual_and_risk_prompt_including_schema_has_reserved_image_budget():
    rows=[dict(id=i,text='Неясни изисквания и зависимости. '*300) for i in range(200)]
    cites=[dict(citation_id='cite_'+'a'*64,quote='Untrusted document text. '*500)]
    messages,schema=analysis_prompt(rows,cites,True)
    assert len(json.dumps(messages,ensure_ascii=False).encode())+len(json.dumps(schema).encode())<=2560
    assert 'Never answer meeting questions' in messages[0]['content']


def test_parent_death_stops_actual_screen_child_process():
    import sys
    from pm_copilot.__main__ import abort_owned_children
    async def check():
        child=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(30)')
        task=asyncio.create_task(asyncio.sleep(30))
        app=SimpleNamespace(state=SimpleNamespace(meeting=SimpleNamespace(stopping=False,processes=[]),documents=SimpleNamespace(stopped=False,task=None,process=None),screen=SimpleNamespace(capture_task=task,worker=None,job=None,native=SimpleNamespace(process=child))))
        abort_owned_children(app);await asyncio.wait_for(child.wait(),3);await asyncio.gather(task,return_exceptions=True)
        assert task.cancelled() and child.returncode is not None
    asyncio.run(check())


@pytest.mark.parametrize('action',['clear_window','broader_sharing'])
def test_turning_off_screen_while_paused_does_not_block_session_resume(m5,action):
    c,native,probe,observer,gen=m5;p,s=start(c)
    wait_until(lambda:c.get('/api/screen').json()['preview_available'])
    assert c.post(f'/api/sessions/{s}/pause').status_code==200
    if action=='clear_window':assert c.put(f'/api/projects/{p}/screen',json={'source_id':None}).status_code==200
    else:assert c.put('/api/sharing',json={'mode':'broader','acknowledged':True}).status_code==200
    response=c.post(f'/api/sessions/{s}/resume')
    assert response.status_code==200 and response.json()['session']['state']=='active'
    assert not response.json()['screen']['preview_available']


@pytest.mark.parametrize('csv_text,valid',[('GPU-123, NVIDIA RTX 4080 Laptop GPU, 12288, 11000\n',True),('bad data\n',False),('GPU-123, GPU, 12288, -5\n',False)])
def test_actual_nvidia_csv_parser_and_loopback_residency_unload_protocol(monkeypatch,csv_text,valid):
    original=httpx.AsyncClient;requests=[]
    class Process:
        returncode=0
        async def communicate(self):return csv_text.encode(),b''
    async def spawn(*args,**kwargs):
        assert args[1]=='--query-gpu=uuid,name,memory.total,memory.free' and 'shell' not in kwargs
        return Process()
    monkeypatch.setattr('pm_copilot.resources.shutil.which',lambda name:'/fixture/nvidia-smi')
    monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
    def handle(request):
        requests.append(request);assert request.url.host=='127.0.0.1' and request.url.port==11434
        if request.method=='GET':return httpx.Response(200,json={'models':[{'name':MODEL,'size_vram':8192*1048576,'context_length':4096}]})
        assert json.loads(request.content)=={'model':MODEL,'keep_alive':0,'stream':False}
        return httpx.Response(200,json={'done':True,'done_reason':'unload'})
    def factory(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handle),**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',factory)
    async def check():
        probe=LocalProbe();result=await probe.sample()
        assert bool(result['gpus'])==valid and result['resident'][0]['size_vram_mib']==8192
        await probe.unload_primary()
    asyncio.run(check());assert len(requests)==2


def test_transcription_backlog_preempts_manual_inference_without_stopping_capture():
    async def check():
        async def notify():pass
        depth=0
        meeting=SimpleNamespace(status=lambda:dict(queue_depth=depth,counts={}),stopping=False)
        resources=Resources(notify,meeting,Probe());resources.interval=.01;entered=asyncio.Event()
        async def manual():
            async with resources.lease('manual'):
                entered.set();await asyncio.sleep(30)
        task=asyncio.create_task(manual());await entered.wait();depth=3;resources.start()
        await asyncio.wait_for(asyncio.gather(task,return_exceptions=True),1)
        assert task.cancelled() and not meeting.stopping and not resources.lock.locked()
        assert any(event['kind']=='preempted' for event in resources.history)
        await resources.close()
    asyncio.run(check())


def test_retry_audio_preserves_running_screen_and_risk_workers(m5):
    c,native,probe,observer,gen=m5;p,s=start(c)
    wait_until(lambda:c.get('/api/screen').json()['preview_available'])
    screen=c.app.state.screen;capture_task=screen.capture_task;worker=screen.worker
    meeting=c.app.state.meeting;calls=[]
    meeting.preflight=lambda options:None
    async def fixture_begin(session_id,options,started_at):calls.append(session_id)
    meeting.begin=fixture_begin
    response=c.post('/api/audio/retry')
    assert response.status_code==200 and calls==[s]
    assert screen.capture_task is capture_task and screen.worker is worker
    assert response.json()['screen']['risks_enabled'] and response.json()['screen']['preview_available']
