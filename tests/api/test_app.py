import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from pm_copilot.app import create_app


def project(client,name='Platform'):
    response=client.post('/api/projects',json={'name':name})
    assert response.status_code==201
    return response.json()['projects'][-1]['id']


def test_project_crud_selection_and_validation(client):
    assert client.get('/api/state').json()['projects']==[]
    for invalid in ['', '  ', 'a\nb', 'x'*121]:
        assert client.post('/api/projects',json={'name':invalid}).status_code==422
    p=project(client)
    assert client.post(f'/api/projects/{p}/select').json()['selected_project_id']==p
    assert client.patch(f'/api/projects/{p}',json={'name':'New name'}).json()['projects'][0]['name']=='New name'
    result=client.delete(f'/api/projects/{p}').json()
    assert result['projects']==[] and result['selected_project_id'] is None
    assert client.patch(f'/api/projects/{p}',json={'name':'Gone'}).status_code==404


def test_session_consent_transitions_and_project_guards(client):
    p=project(client)
    other=project(client,'Other')
    client.post(f'/api/projects/{p}/select')
    assert client.post('/api/sessions',json={'consent':False,'project_id':p}).status_code==422
    result=client.post('/api/sessions',json={'consent':True,'project_id':p}).json()
    s=result['session']['id']
    assert result['session']['state']=='active'
    assert result['capabilities']=={'audio_capture':False,'assistance':True}
    assert client.post('/api/sessions',json={'consent':True,'project_id':p}).status_code==409
    assert client.delete(f'/api/projects/{p}').status_code==409
    assert client.post(f'/api/projects/{other}/select').status_code==409
    assert client.post(f'/api/sessions/{s}/resume').status_code==409
    assert client.post(f'/api/sessions/{s}/pause').json()['session']['state']=='paused'
    assert client.post(f'/api/sessions/{s}/pause').status_code==409
    assert client.post(f'/api/sessions/{s}/resume').json()['session']['state']=='active'
    assert client.post(f'/api/sessions/{s}/stop').json()['session']['ended_at']
    assert client.post(f'/api/sessions/{s}/resume').status_code==409
    assert client.post(f'/api/projects/{other}/select').status_code==200


def test_state_persists_and_live_session_recovers_interrupted(tmp_path):
    db=tmp_path/'persist.sqlite3'
    def connect():
        return TestClient(create_app(db,'test-secret','http://127.0.0.1:8750'),base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'})
    with connect() as c:
        p=project(c)
        c.post(f'/api/projects/{p}/select')
        c.post('/api/sessions',json={'consent':True,'project_id':p})
        revision=c.get('/api/state').json()['revision']
    with connect() as c:
        state=c.get('/api/state').json()
        assert state['selected_project_id']==p
        assert state['session']['state']=='interrupted'
        assert state['session']['ended_at']
        assert state['revision']>revision
        assert c.post('/api/sessions',json={'consent':True,'project_id':p}).status_code==201


def test_auth_host_origin_and_no_data_leak(client):
    assert client.get('/api/state',headers={'Authorization':''}).status_code==401
    assert client.get('/api/state',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.post('/api/projects',json={'name':'Attack'},headers={'Origin':'https://attacker.invalid'}).status_code==403
    assert client.get('/api/state',headers={'Host':'attacker.invalid'}).status_code==403
    assert client.get('/api/state',headers={'Origin':'null'}).status_code==403
    assert client.get('/api/state').json()['projects']==[]
    assert client.get('/api/state').headers['cache-control']=='no-store'


def test_events_auth_and_broadcast_to_two_views(client):
    with client.websocket_connect('ws://127.0.0.1:8750/api/events',headers={'Origin':'http://127.0.0.1:8750'}) as one, client.websocket_connect('ws://127.0.0.1:8750/api/events',headers={'Origin':'http://127.0.0.1:8750'}) as two:
        for ws in (one,two):
            ws.send_json({'token':'test-secret'})
            assert ws.receive_json()['state']['revision']==0
        project(client)
        a,b=one.receive_json(),two.receive_json()
        assert a==b and a['version']==1 and len(a['state']['projects'])==1
    with client.websocket_connect('ws://127.0.0.1:8750/api/events',headers={'Origin':'http://127.0.0.1:8750'}) as ws:
        ws.send_json({'token':'wrong'})
        with pytest.raises(WebSocketDisconnect): ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('ws://127.0.0.1:8750/api/events',headers={'Origin':'https://attacker.invalid'}): pass


def test_schema_and_shortcut_validation(client):
    schema=client.get('/api/schema').json()
    import json
    from pathlib import Path
    assert schema == json.loads((Path(__file__).resolve().parents[2]/'packages/contracts/openapi.json').read_text())
    assert 'Snapshot' in schema['components']['schemas']
    assert '/api/projects' in schema['paths']
    assert client.put('/api/settings/shortcut',json={'accelerator':'not valid'}).status_code==422
    assert client.put('/api/settings/shortcut',json={'accelerator':'Control+Alt+P'}).json()['shortcut']=='Control+Alt+P'


def test_delete_cascades_only_target_history(client):
    a=project(client,'Alpha')
    b=project(client,'Beta')
    for p in (a,b):
        client.post(f'/api/projects/{p}/select')
        s=client.post('/api/sessions',json={'consent':True,'project_id':p}).json()['session']['id']
        client.post(f'/api/sessions/{s}/stop')
    state=client.delete(f'/api/projects/{a}').json()
    assert {s['project_id'] for s in state['sessions']}=={b}
    assert [p['id'] for p in state['projects']]==[b]


def test_stale_project_start_does_not_cross_project_boundary(client):
    a=project(client,'Alpha')
    b=project(client,'Beta')
    client.post(f'/api/projects/{a}/select')
    client.post(f'/api/projects/{b}/select')
    assert client.post('/api/sessions',json={'consent':True,'project_id':a}).status_code==409
    assert client.get('/api/state').json()['session'] is None
