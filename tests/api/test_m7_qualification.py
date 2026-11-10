"""Collector failure modes use an injected clock/telemetry, never qualify this host."""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pm_copilot.store import Store, DomainError
from pm_copilot.resources import ResourceSettings
from pm_copilot.document_parser import parse_document
from pm_copilot.questions import Question
from test_assistance import FixtureGeneration, payload
import pm_copilot.qualification as module


def test_qualification_endpoints_require_actual_live_capture_and_auth(client):
    assert client.get('/api/qualification').json()['release_qualified'] is False
    for route in ('start','finish'):
        assert client.post('/api/qualification/'+route).status_code==409
    assert client.get('/api/qualification/report').status_code==409
    assert client.post('/api/qualification/start',headers={'Authorization':''}).status_code==401


@pytest.mark.parametrize('fault', [None, 'short', 'pause', 'gpu', 'drops', 'no_native_report', 'config', 'model', 'citation', 'no_questions', 'capacity'])
def test_collector_measured_checks_are_fail_closed(tmp_path, monkeypatch, fault):
    async def check():
        clock=[100.]
        monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:clock[0]))
        monkeypatch.setattr(module,'sys',SimpleNamespace(platform='win32'))
        monkeypatch.setattr(module,'resident_mib',lambda:100.)
        store=Store(tmp_path/'qualification.sqlite3'); pid=store.create('Private')['projects'][0]['id'];store.select(pid)
        sid=store.start(pid,True)['session']['id']
        counts={'segments':0,'packets':0,'native_dropped_packets':0}
        meeting_state={'state':'capturing','session_id':sid,'counts':counts,'queue_depth':0,'error':None}
        meeting=SimpleNamespace(status=lambda:meeting_state)
        telemetry={'gpus':[dict(uuid='GPU-fixture',name='RTX 4080 Laptop GPU TEST FIXTURE',total_mib=12288,free_mib=3072)],
                   'resident':[dict(model=FixtureGeneration.model,size_vram_mib=8192,context=4096)],'samples_age_ms':0}
        async def refresh():return telemetry
        resources=SimpleNamespace(settings=ResourceSettings(),refresh=refresh,status=lambda:telemetry)
        generator=FixtureGeneration()
        recorder=module.Qualification(store,meeting,resources,SimpleNamespace(generator=generator))
        await recorder.start()
        assert recorder.status()['phase']=='recording'
        with pytest.raises(DomainError):await recorder.start()
        doc=store.upload_document(pid,'evidence.txt',b'Friday release evidence')
        store.commit_parsed(pid,doc['document_id'],doc['revision_id'],parse_document('evidence.txt',b'Friday release evidence'))
        cid=store.revision_chunks(pid,doc['revision_id'])[0]['id']
        for i in range(15):
            rid=str(uuid4());question=SimpleNamespace(text='When is release?',segment_ids=(1,)) if i<10 or fault=='no_questions' else None
            store.record_assistance(rid,pid,sid,0,1,'a'*64,question,[])
            if question:
                store.save_response(rid,payload(cid),generator.model,'b'*64 if fault=='model' else generator.digest,{})
                store.finish_assistance(rid,'completed',None,1000)
        store.add_segment(sid,'local',0,1,'PRIVATE TRANSCRIPT CANARY','en','en')
        store.add_segment(sid,'remote',0,1,'PRIVATE TRANSCRIPT CANARY','bg','bg')
        for i in range(1,2701 if fault!='short' else 11):
            clock[0]+=2
            counts.update(segments=i,packets=i*40,last_chunk_lag_ms=1000,local_audible_packets=i,remote_audible_packets=i)
            if fault=='pause' and i==5:store.transition(sid,'pause')
            if fault=='gpu' and i==5:telemetry['samples_age_ms']=10000
            if fault=='config' and i==5:resources.settings.force_cpu=True
            recorder._sample()
        if fault=='drops':counts['dropped_chunks']=1
        if fault=='no_native_report':counts.pop('native_dropped_packets')
        if fault=='citation':store.delete_document(pid,doc['document_id'])
        if fault=='capacity':recorder.samples[:]=[recorder.samples[-1]]*module.MAX_SAMPLES;recorder._sample()
        with pytest.raises(DomainError,match='Stop the session'):await recorder.finish()
        store.transition(sid,'stop');meeting_state['state']='idle'
        report=await recorder.finish()
        assert report['telemetry_passed'] is (fault is None),report['checks']
        assert report['release_qualified'] is False
        assert 'PRIVATE TRANSCRIPT CANARY' not in json.dumps(report)
        assert len(recorder.samples)<=module.MAX_SAMPLES
        store.close()
    asyncio.run(check())


def test_collector_refuses_wrong_hardware_and_cancel_cleans_up(tmp_path,monkeypatch):
    async def check():
        store=Store(tmp_path/'cancel.sqlite3');pid=store.create('Cancel')['projects'][0]['id'];store.select(pid);sid=store.start(pid,True)['session']['id']
        meeting=SimpleNamespace(status=lambda:dict(state='capturing',session_id=sid,counts={},queue_depth=0))
        async def refresh():return dict(gpus=[])
        resources=SimpleNamespace(refresh=refresh,settings=ResourceSettings())
        recorder=module.Qualification(store,meeting,resources,SimpleNamespace(generator=FixtureGeneration()))
        with pytest.raises(DomainError,match='Windows'):await recorder.start()
        await recorder.close();assert recorder.task is None
        store.close()
    asyncio.run(check())
