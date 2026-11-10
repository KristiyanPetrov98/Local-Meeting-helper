"""Portable sustained integration. Explicit subprocess/PNG/model fixtures, not laptop qualification."""
import asyncio
import base64
import json
import os
from pathlib import Path
import statistics
import sys
import textwrap
import time
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from conftest import NoModelEmbeddings
from pm_copilot.app import create_app
from pm_copilot.meeting import Meeting
from pm_copilot.qualification import resident_mib
from test_app import project
from test_assistance import FixtureGeneration, finished, trigger
from test_documents import upload, finished as indexed
from test_m5 import Native, Observer, Probe


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX subprocess fixture; real Windows media is a separate release gate')
def test_sustained_capture_rag_generation_screen_privacy_and_restart(tmp_path):
    seconds = float(os.environ.get('PM_M7_SOAK_SECONDS', '12'))
    assert 10 <= seconds <= 120
    userdata = tmp_path / 'userdata'; userdata.mkdir()
    helper = tmp_path / 'capture_fixture'; worker = tmp_path / 'asr_fixture.py'
    helper.write_text('#!' + sys.executable + '\n' + textwrap.dedent('''
        import sys,json,base64,time,threading
        from array import array
        json.loads(sys.stdin.readline());print(json.dumps({'type':'started'}),flush=True)
        stopped=threading.Event()
        threading.Thread(target=lambda:(sys.stdin.readline(),stopped.set()),daemon=True).start()
        pcm=base64.b64encode(array('f',[.142857]*1600).tobytes()).decode()
        for i in range(3000):
            if stopped.is_set():break
            for source in ('local','remote'):
                print(json.dumps({'type':'audio','source':source,'sequence':i,'start':i*.1,'samples':1600,'sample_rate':16000,'pcm':pcm}),flush=True)
            time.sleep(.1)
        print(json.dumps({'type':'stopped','dropped_packets':0}),flush=True)
    ''')); helper.chmod(0o700)
    worker.write_text(textwrap.dedent('''
        import sys,json,time
        i=0
        for line in sys.stdin:
            json.loads(line);time.sleep(.05);i+=1
            print(json.dumps({'type':'result','language':'bg' if i%2 else 'en','segments':[{'start':0,'end':2,'text':'When is the release?'}]}),flush=True)
    '''))
    class FixtureMeeting(Meeting):
        def diagnostics(self): return dict(available=True,reason=None,process_loopback=False,diarization_model_present=False)
        async def _spawn_worker(self, mode):
            process = await asyncio.create_subprocess_exec(sys.executable,'-u',str(worker),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
            self.processes.append(process); return process
        def __init__(self,*args): super().__init__(*args); self.helper=helper
    native, probe, observer, generator = Native(), Probe(), Observer(), FixtureGeneration()
    generator.delay = .15
    database = userdata / 'meeting.sqlite3'
    app = create_app(database,'m7-secret','http://127.0.0.1:8750',meeting_factory=FixtureMeeting,
                     embedding_factory=NoModelEmbeddings,generation_factory=lambda:generator,
                     resource_probe=probe,screen_native_factory=lambda:native,observation_factory=lambda:observer)
    starts=[]; latencies=[]; rss=[]; maximum_queue=0; counts={}
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer m7-secret'}) as c:
        pid=project(c,'Isolated Alpha'); other=project(c,'Isolated Beta')
        for scope, text in ((pid,'The release is scheduled for Friday.'),(other,'The release is scheduled for Monday.')):
            doc=upload(c,scope,'release.txt',text).json(); assert indexed(c,scope,doc['document_id'])['status']=='lexical_ready'
        c.post(f'/api/projects/{pid}/select')
        assert c.put('/api/sharing',json={'mode':'tab','acknowledged':True}).status_code==200
        assert c.put(f'/api/projects/{pid}/screen',json={'source_id':'123:456'}).status_code==200
        response=c.post('/api/sessions',json={'project_id':pid,'consent':True,'capture':True,'screen':True,'risks':True})
        assert response.status_code==201,response.text
        sid=response.json()['session']['id']; base=f'/api/projects/{pid}/sessions/{sid}/assistance'
        rid=str(uuid4()); assert trigger(c,base,rid).json()['status']=='no_question'
        assert generator.calls==0
        started=time.monotonic(); next_request=started+4.2
        while time.monotonic()-started<seconds:
            state=c.get('/api/state').json(); maximum_queue=max(maximum_queue,state['meeting']['queue_depth'])
            memory=resident_mib()
            if memory is not None:rss.append(memory)
            if state['meeting']['counts'].get('segments',0) and time.monotonic()>=next_request:
                before=state['meeting']['counts']['packets']; request_start=time.monotonic(); rid=str(uuid4())
                assert trigger(c,base,rid).status_code==202
                result=finished(c,base,rid,'completed');latencies.append((time.monotonic()-request_start)*1000)
                assert result['citations'] and not result['unavailable_citations']
                assert all(x['quote']=='The release is scheduled for Friday.' for x in result['citations'])
                assert c.get(f'/api/projects/{other}/sessions/{sid}/assistance/{rid}').status_code==404
                after=c.get('/api/state').json()['meeting']['counts']['packets'];starts.append((before,after))
                next_request=time.monotonic()+1
            time.sleep(.05)
        state=c.get('/api/state').json();counts=state['meeting']['counts']
        assert counts['packets']>100 and counts['segments']>0 and generator.calls>0 and observer.observations>0
        assert counts['gaps']==counts['dropped_chunks']==counts['asr_errors']==0
        assert maximum_queue<=8 and all(after>before for before,after in starts)
        assert c.put('/api/sharing',json={'mode':'broader','acknowledged':True}).status_code==200
        assert c.get('/api/state').json()['screen']['state']!='capturing'
        packets=c.get('/api/state').json()['meeting']['counts']['packets'];time.sleep(.3)
        assert c.get('/api/state').json()['meeting']['counts']['packets']>packets
        assert c.post(f'/api/sessions/{sid}/stop').status_code==200
        assert app.state.meeting.counts['native_dropped_packets']==0 and app.state.meeting.error is None
        assert not app.state.meeting.processes and not app.state.meeting.tasks and app.state.meeting.queue.empty()
    # Scan only application data, not the explicit fixture source or model/input files.
    from array import array
    pcm=array('f',[.142857]*1600).tobytes()
    from test_m5 import frame
    png=base64.b64decode(frame()['png'])
    for path in userdata.rglob('*'):
        if path.is_file():
            content=path.read_bytes()
            assert pcm not in content and base64.b64encode(pcm) not in content
            assert png not in content and base64.b64encode(png) not in content
            assert b'm7-secret' not in content
    with TestClient(create_app(database,'fresh-secret','http://127.0.0.1:8750',embedding_factory=NoModelEmbeddings),
                    base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer fresh-secret'}) as c:
        assert c.get('/api/state').json()['session']['state']=='stopped'
        transcript=c.get(f'/api/projects/{pid}/sessions/{sid}/transcript').json()
        assert transcript['segments']
        assert c.get(f'/api/projects/{other}/sessions/{sid}/transcript').status_code==404
    report={'scope':'Portable fixture integration; real subprocess pipes, parser, SQLite, PNG decoding and orchestration. No WASAPI, WGC, Whisper or Ollama inference.',
            'duration_seconds':time.monotonic()-started,'status':'passed','audio_counts':counts,'maximum_queue_depth':maximum_queue,
            'manual_requests':len(latencies),'manual_fixture_latency_median_ms':statistics.median(latencies),
            'backend_rss_start_mib':rss[0] if rss else None,'backend_rss_end_mib':rss[-1] if rss else None,
            'backend_rss_max_mib':max(rss) if rss else None,'media_and_token_canaries_absent':True,
            'restart_and_project_isolation_passed':True,'target_hardware_qualified':False}
    if os.environ.get('PM_M7_SOAK_OUTPUT'):Path(os.environ['PM_M7_SOAK_OUTPUT']).write_text(json.dumps(report,indent=2)+'\n')
