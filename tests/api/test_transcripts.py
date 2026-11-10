import asyncio
import base64
import json
import math
from array import array
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from pm_copilot.audio import Chunks, SpeakerStitcher, packet
from pm_copilot.meeting import Meeting, AudioOptions
from pm_copilot.store import Store
from test_app import project


def session(client, name='Transcript project'):
    p=project(client,name)
    client.post(f'/api/projects/{p}/select')
    s=client.post('/api/sessions',json={'consent':True,'project_id':p}).json()['session']['id']
    return p,s


def test_packet_validation_and_gap_integrity():
    data=array('f',[.2]*1600).tobytes()
    msg={'source':'remote','sequence':0,'start':0.,'sample_rate':16000,'samples':1600,'pcm':base64.b64encode(data).decode()}
    assert packet(msg)[3]==data
    for field,value in [('sample_rate',48000),('samples',9999999),('start',float('nan')),('source','invalid'),('pcm','!!!')]:
        with pytest.raises(ValueError): packet({**msg,field:value})
    chunks=Chunks(seconds=.2)
    assert chunks.push(0,0,data)==([],False)
    output,gap=chunks.push(1,.1,data)
    assert not gap and output==[(0,data+data)]
    chunks.push(2,.2,data)
    assert chunks.push(4,.4,data)==([],True)
    assert len(chunks.pending)==6400
    assert chunks.flush()==(.4,data)
    assert chunks.flush() is None


def test_speaker_ids_follow_overlap_not_model_local_names():
    stitch=SpeakerStitcher()
    first=stitch.assign([{'start':0,'end':20,'label':'A'},{'start':20,'end':30,'label':'B'}],0)
    second=stitch.assign([{'start':0,'end':10,'label':'X'},{'start':10,'end':20,'label':'Y'}],20)
    assert second[0]['speaker']==first[1]['speaker']
    assert second[1]['speaker'] not in {t['speaker'] for t in first}


def test_transcript_project_isolation_rename_merge_persistence(client):
    p,s=session(client)
    store=client.app.state.store
    store.add_segment(s,'remote',0,2,'Hello project','en','a')
    store.add_segment(s,'local',3,5,'Здравей проект','bg','b')
    page=client.get(f'/api/projects/{p}/sessions/{s}/transcript').json()
    assert len(page['segments'])==2
    assert {x['language'] for x in page['segments']}=={'en','bg'}
    one,two=[x['id'] for x in page['speakers']]
    assert client.patch(f'/api/projects/{p}/sessions/{s}/speakers/{one}',json={'name':'Facilitator'}).status_code==200
    assert client.post(f'/api/projects/{p}/sessions/{s}/speakers/{two}/merge',json={'target':one}).status_code==200
    merged=client.get(f'/api/projects/{p}/sessions/{s}/transcript').json()
    assert len(merged['speakers'])==1
    assert {x['speaker_id'] for x in merged['segments']}=={one}
    other=project(client,'Other')
    assert client.get(f'/api/projects/{other}/sessions/{s}/transcript').status_code==404
    assert client.patch(f'/api/projects/{other}/sessions/{s}/speakers/{one}',json={'name':'Attack'}).status_code==404
    # Source labels are canonicalized after a manual merge, including later segments.
    store.add_segment(s,'local',6,7,'New sentence','en','c')
    assert store.transcript(p,s)['segments'][-1]['speaker_id']==one


def test_speaker_merge_cannot_target_another_session(client):
    p,s=session(client)
    store=client.app.state.store;store.add_segment(s,'remote',0,1,'one','en','a')
    one=store.transcript(p,s)['speakers'][0]['id']
    client.post(f'/api/sessions/{s}/stop')
    s2=client.post('/api/sessions',json={'consent':True,'project_id':p}).json()['session']['id']
    store.add_segment(s2,'remote',0,1,'two','en','b')
    two=store.transcript(p,s2)['speakers'][0]['id']
    assert client.post(f'/api/projects/{p}/sessions/{s}/speakers/{one}/merge',json={'target':two}).status_code==404


def test_echo_dedupe_and_repeated_segment_key(client):
    p,s=session(client);store=client.app.state.store
    store.add_segment(s,'local',0,3,'The release date is next Monday','en','a',True)
    store.add_segment(s,'remote',.1,3.1,'The release date is next Monday','en','b',True)
    store.add_segment(s,'remote',.1,3.1,'The release date is next Monday','en','b',True)
    page=store.transcript(p,s)
    assert len(page['segments'])==1 and page['segments'][0]['source']=='remote'
    store.add_segment(s,'local',10,12,'The release date is next Monday','en','c',True)
    assert len(store.transcript(p,s)['segments'])==2


def test_pagination_and_retention(client):
    p,s=session(client);store=client.app.state.store
    for i in range(205): store.add_segment(s,'remote',i,i+1,f'segment {i}','en',str(i))
    latest=client.get(f'/api/projects/{p}/sessions/{s}/transcript').json()
    assert len(latest['segments'])==200
    older=client.get(f'/api/projects/{p}/sessions/{s}/transcript?before={latest["older_cursor"]}').json()
    assert len(older['segments'])==5
    with store.db: store.db.execute('UPDATE transcript_segments SET created_at=?',((datetime.now(timezone.utc)-timedelta(days=31)).isoformat(),))
    client.put('/api/settings/retention',json={'days':30})
    assert client.get(f'/api/projects/{p}/sessions/{s}/transcript').json()['segments']==[]
    assert client.put('/api/settings/retention',json={'days':0}).status_code==422


def test_audio_settings_persist_and_missing_windows_is_honest(client):
    options={'microphone':'default','loopback':'default','language':'bg','device':'cpu','echo_profile':'speakers','diarization':False}
    assert client.put('/api/audio/settings',json=options).status_code==200
    assert client.get('/api/audio/settings').json()==options
    p=project(client);client.post(f'/api/projects/{p}/select')
    response=client.post('/api/sessions',json={'consent':True,'project_id':p,'capture':True})
    assert response.status_code==503
    assert client.get('/api/state').json()['session'] is None
    assert client.get('/api/audio/devices').json()['devices']==[]


def test_capture_queue_stays_bounded_when_inference_is_busy():
    async def check():
        async def notify(): pass
        meeting=Meeting(notify,notify,notify)
        meeting.counts={'dropped_chunks':0}
        for i in range(100): meeting._enqueue('remote',i*4,b'\x00'*256000)
        assert meeting.queue.qsize()==8 and meeting.counts['dropped_chunks']==92
        assert 'capture is continuing' in meeting.error
        await meeting.stop(flush=False)
        assert meeting.queue.empty() and not meeting.chunks
    asyncio.run(check())


def test_transcript_survives_database_reopen(tmp_path):
    path=tmp_path/'persistent.sqlite3'
    store=Store(path);store.create('Persist');p=store.snapshot()['projects'][0]['id'];store.select(p);s=store.start(p,True)['session']['id']
    store.add_segment(s,'remote',0,2,'Persisted text only','en','a');store.close()
    store=Store(path)
    assert store.transcript(p,s)['segments'][0]['text']=='Persisted text only'
    columns={x[1] for x in store.db.execute('PRAGMA table_info(transcript_segments)')}
    assert not columns.intersection({'pcm','audio','waveform','image'})
    assert set(x.name for x in tmp_path.iterdir())<={'persistent.sqlite3','persistent.sqlite3-wal','persistent.sqlite3-shm'}
    store.close()


def test_manual_corrections_are_not_overwritten_by_background_diarization(client):
    p,s=session(client);store=client.app.state.store
    store.add_segment(s,'remote',0,2,'Manual correction','en','a')
    speaker=store.transcript(p,s)['speakers'][0]['id']
    client.patch(f'/api/projects/{p}/sessions/{s}/speakers/{speaker}',json={'name':'Reviewed speaker'})
    store.refine_speakers(s,[{'start':0,'end':2,'speaker':'speaker-1'}])
    assert store.transcript(p,s)['segments'][0]['speaker_id']==speaker
    assert store.transcript(p,s)['speakers'][0]['name']=='Reviewed speaker'


def test_overlapping_chunks_retain_exact_overlap():
    chunks=Chunks(seconds=1,overlap_seconds=.5)
    pcm=array('f',[.2]*1600).tobytes()
    output=[]
    for i in range(15): output.extend(chunks.push(i,i*.1,pcm)[0])
    assert [round(t,2) for t,_ in output]==[0,.5]
    assert all(len(pcm)==64000 for _,pcm in output)
    assert len(chunks.pending)==32000


def test_project_delete_cascades_transcript_and_speaker_aliases(client):
    p,s=session(client);store=client.app.state.store
    store.add_segment(s,'remote',0,2,'First speaker','en','a')
    store.add_segment(s,'local',3,5,'Second speaker','en','b')
    a,b=[row['id'] for row in store.transcript(p,s)['speakers']]
    store.merge_speakers(p,s,a,b)
    client.post(f'/api/sessions/{s}/stop')
    assert client.delete(f'/api/projects/{p}').status_code==200
    assert store.db.execute('SELECT COUNT(*) FROM transcript_segments WHERE session_id=?',(s,)).fetchone()[0]==0
    assert store.db.execute('SELECT COUNT(*) FROM speakers WHERE session_id=?',(s,)).fetchone()[0]==0


def test_devices_can_be_reconfigured_while_paused_without_switching_project(client):
    p,s=session(client)
    assert client.put('/api/audio/settings',json={'language':'bg'}).status_code==409
    client.post(f'/api/sessions/{s}/pause')
    assert client.put('/api/audio/settings',json={'language':'bg','microphone':'replacement-device'}).status_code==200
    assert client.post(f'/api/sessions/{s}/resume').status_code==200
    assert client.get('/api/state').json()['session']['project_id']==p
