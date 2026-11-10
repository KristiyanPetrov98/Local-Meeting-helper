"""Pipeline plumbing using explicit test-only subprocess fixtures, not real ASR or WASAPI."""
import asyncio
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
import pytest
from pm_copilot.meeting import Meeting, AudioOptions


@pytest.mark.skipif(sys.platform=='win32',reason='POSIX executable fixture; Windows capture uses the native helper')
def test_slow_model_does_not_block_capture_and_shutdown_releases_media(tmp_path):
    helper=tmp_path/'fixture_capture'
    helper.write_text('#!'+sys.executable+'\n'+textwrap.dedent('''
        import sys,json,base64,time
        from array import array
        json.loads(sys.stdin.readline())
        print(json.dumps({'type':'started'}),flush=True)
        pcm=base64.b64encode(array('f',[.1]*1600).tobytes()).decode()
        for i in range(500):
            print(json.dumps({'type':'audio','source':'remote','sequence':i,'start':i*.1,'samples':1600,'sample_rate':16000,'pcm':pcm}),flush=True)
            time.sleep(.001)
        time.sleep(10)
    '''));helper.chmod(0o700)
    worker=tmp_path/'fixture_asr.py'
    worker.write_text(textwrap.dedent('''
        import sys,json,time
        for line in sys.stdin:
            json.loads(line);time.sleep(.2)
            print(json.dumps({'type':'result','language':'bg','segments':[{'start':0,'end':2,'text':'Test fixture only'}]}),flush=True)
    '''))
    async def check():
        segments=[]
        async def notify(): pass
        async def segment(*args): segments.append(args)
        class FixtureMeeting(Meeting):
            async def _spawn_worker(self,mode):
                process=await asyncio.create_subprocess_exec(sys.executable,'-u',str(worker),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE)
                self.processes.append(process);return process
        meeting=FixtureMeeting(notify,segment,notify);meeting.helper=helper
        await meeting.begin('fixture-session',AudioOptions(microphone=None),datetime.now(timezone.utc).isoformat())
        async def wait_packets():
            while meeting.counts.get('packets',0)<500: await asyncio.sleep(.01)
        from pm_copilot.resources import Resources
        from types import SimpleNamespace
        async def sample():return dict(gpus=[],resident=[],reason='Explicit test-only CPU telemetry')
        resources=Resources(notify,meeting,SimpleNamespace(sample=sample))
        async with resources.lease('manual'):
            await asyncio.wait_for(wait_packets(),5)
            assert resources.owner=='manual' and segments
        assert meeting.counts['packets']==500
        assert meeting.counts['dropped_chunks']>0
        assert meeting.queue.qsize()<=8
        # It is actual interprocess plumbing with deliberate slow fixture ASR, not proof of model speed.
        await asyncio.wait_for(meeting.stop(),10)
        assert segments and segments[0][0]=='fixture-session' and segments[0][5]=='bg'
        assert not meeting.processes and not meeting.tasks and meeting.queue.empty()
        count=len(segments);await asyncio.sleep(.3);assert len(segments)==count
    asyncio.run(check())


def test_inference_failure_keeps_capture_running_and_attempts_cpu_recovery():
    async def check():
        async def notify(): pass
        class Process:
            returncode=None
            def kill(self): self.returncode=-9
            async def wait(self): return self.returncode
        class FixtureMeeting(Meeting):
            async def _request(self,process,pcm,timeout=120): raise RuntimeError('fixture_gpu_oom')
            async def _spawn_worker(self,mode):
                assert self.asr_device=='cpu'
                raise RuntimeError('fixture_cpu_start_failed')
        meeting=FixtureMeeting(notify,notify,notify)
        meeting.epoch=1;meeting.counts={'asr_errors':0};meeting.asr_device='cuda'
        capture=Process();meeting.capture_process=capture
        meeting.queue.put_nowait(('remote',0,array_bytes()))
        await meeting._asr_loop(Process(),1)
        assert capture.returncode is None and not meeting.stopping
        assert meeting.counts['asr_cpu_fallback']==1
        assert 'Capture continues' in meeting.error
    def array_bytes():
        from array import array
        return array('f',[.1]*1600).tobytes()
    asyncio.run(check())


def test_resume_retains_session_diagnostics_and_never_reuses_provisional_ids():
    async def check():
        async def notify(): pass
        meeting=Meeting(notify,notify,notify)
        meeting.session_id='same-session';meeting.counts={'dropped_chunks':7};meeting.stitcher.next_id=4
        await meeting.begin('same-session',AudioOptions(),datetime.now(timezone.utc).isoformat())
        assert meeting.stitcher.next_id==4 and meeting.counts['dropped_chunks']==7
        await meeting.stop(flush=False)
    asyncio.run(check())


def test_parent_death_kills_owned_children_without_waiting_for_http_draining():
    from types import SimpleNamespace
    from pm_copilot.__main__ import abort_owned_children
    async def check():
        children=[await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(30)') for _ in range(2)]
        pending=asyncio.create_task(asyncio.sleep(30))
        meeting=SimpleNamespace(stopping=False,processes=[children[0]])
        documents=SimpleNamespace(stopped=False,task=pending,process=children[1])
        app=SimpleNamespace(state=SimpleNamespace(meeting=meeting,documents=documents))
        abort_owned_children(app)
        await asyncio.wait_for(asyncio.gather(*(p.wait() for p in children)),3)
        await asyncio.gather(pending,return_exceptions=True)
        assert meeting.stopping and documents.stopped and pending.cancelled()
        assert all(p.returncode is not None for p in children)
    asyncio.run(check())
