from types import MethodType
import pytest
from test_m6 import setup_client,finished

@pytest.mark.parametrize('license,network',[(False,True),(True,False)])
def test_prepare_requires_explicit_one_time_acknowledgement(setup_client,license,network):
    c=setup_client
    assert c.post('/api/setup/prepare',json={'license_acknowledged':license,'network_acknowledged':network}).status_code==422
    assert c.get('/api/setup').json()['runs']==[]

def test_prepare_sequences_exact_models_and_actual_check_results(setup_client,monkeypatch):
    c=setup_client;setup=c.app.state.setup;calls=[]
    async def install(self,kind,params,temporary):calls.append((kind,params['model_id']));return dict(model_id=params['model_id'],files_installed=True,inference_verified=False)
    required=['storage','local_rag','parser_worker','generation','embedding','asr_runtime','audio_enumeration','window_enumeration']
    async def checks(self):return {'checks':[dict(id=k,status='passed') for k in required]+[dict(id='diarization_runtime',status='blocked')],'all_passed':False}
    monkeypatch.setattr(setup,'install',MethodType(install,setup));monkeypatch.setattr(setup,'self_tests',MethodType(checks,setup))
    response=c.post('/api/setup/prepare',json=dict(license_acknowledged=True,network_acknowledged=True));assert response.status_code==202
    run=finished(c,response.json()['id']);assert run['status']=='completed'
    assert calls==[('download','generation'),('download','embedding'),('download','whisper-medium')]
    assert run['report']['required_runtime_ready'] is True and run['report']['all_passed'] is False and run['report']['release_qualified'] is False

def test_prepare_reuses_snapshot_and_fails_when_required_checks_fail(setup_client,monkeypatch):
    c=setup_client;setup=c.app.state.setup;calls=[];(setup.models/'whisper-medium').mkdir()
    async def install(self,kind,params,temporary):calls.append((kind,params['model_id']));return {'files_installed':True}
    async def checks(self):return {'checks':[dict(id='generation',status='failed')],'all_passed':False}
    monkeypatch.setattr(setup,'install',MethodType(install,setup));monkeypatch.setattr(setup,'self_tests',MethodType(checks,setup))
    response=c.post('/api/setup/prepare',json=dict(license_acknowledged=True,network_acknowledged=True))
    run=finished(c,response.json()['id']);assert run['status']=='completed' and run['report']['required_runtime_ready'] is False
    assert calls[-1]==('verify','whisper-medium')
