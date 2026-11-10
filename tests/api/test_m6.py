"""Setup tests use explicit runtime/ASR fixtures; no physical-device qualification."""
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from conftest import NoHardwareMeeting,NoModelEmbeddings
from pm_copilot.app import create_app
from pm_copilot.briefing import MODEL
from pm_copilot.model_assets import install_snapshot,verify_snapshot,validate_snapshot
from pm_copilot.runtime import command
from test_app import project
from test_assistance import FixtureGeneration,payload


def test_offline_rag_check_handles_equal_project_timestamps(tmp_path,monkeypatch):
    from pm_copilot import store
    from pm_copilot.setup_checks import core_checks
    monkeypatch.setattr(store,'now',lambda:'2026-11-10T00:00:00+00:00')
    ids=iter(['z-alpha','a-beta'])
    monkeypatch.setattr(store,'uuid4',lambda:next(ids))
    result=next(row for row in core_checks(tmp_path) if row['id']=='local_rag')
    assert result['status']=='passed',result


def finished(c,rid):
    for _ in range(600):
        row=next(r for r in c.get('/api/setup').json()['runs'] if r['id']==rid)
        if row['status']!='running':return row
        time.sleep(.01)
    pytest.fail('Setup operation did not finish')


def snapshot(path):
    path.mkdir();(path/'model.bin').write_bytes(b'Explicit non-working test weights')
    for name in ('config.json','tokenizer.json'):(path/name).write_text('{}')
    return path


@pytest.fixture
def setup_client(tmp_path):
    app=create_app(tmp_path/'m6.sqlite3','test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=NoModelEmbeddings,desktop_capability='desktop-test-capability')
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:yield c


def test_setup_defaults_auth_and_no_automatic_operations(setup_client):
    c=setup_client;state=c.get('/api/setup').json()
    assert not state['busy'] and not state['completed'] and state['runs']==[] and state['selected_profile'] is None
    assert all(asset['inference_verified'] is False for asset in state['assets'])
    assert c.get('/api/setup',headers={'Authorization':''}).status_code==401
    assert c.post('/api/setup/self-test',headers={'Origin':'https://attacker.invalid'}).status_code==403


def test_hardware_diagnostics_are_observations_not_inference_results(setup_client):
    result=setup_client.get('/api/setup/diagnostics').json()
    assert result['logical_cpus']>0 and result['disk_free_bytes']>0
    assert result['generation_model']==MODEL and 'do not establish' in result['qualification']
    assert setup_client.get('/api/setup').json()['runs']==[]


@pytest.mark.parametrize('body',[{'asr_size':'large'},{'asr_device':'remote'},{'reserve_mib':0},{'generation_budget_mib':1},{'endpoint':'https://cloud.invalid'}])
def test_configuration_rejects_unknown_profiles_remote_endpoints_and_invalid_budgets(setup_client,body):
    assert setup_client.put('/api/setup/configuration',json=body).status_code==422


def test_configuration_persists_and_never_changes_primary_model(setup_client):
    c=setup_client;r=c.put('/api/setup/configuration',json=dict(asr_size='small',asr_device='cpu',reserve_mib=3072,generation_budget_mib=8192,force_cpu=True))
    assert r.status_code==200 and r.json()['preferences']['asr_size']=='small'
    assert c.app.state.meeting.model==c.app.state.setup.models/'whisper-small'
    assert c.app.state.assistance.generator.model==MODEL
    assert c.get('/api/state').json()['resources']['settings']['force_cpu']


@pytest.mark.parametrize('body',[{'model_id':'unapproved','license_acknowledged':True,'network_acknowledged':True},{'model_id':'generation','license_acknowledged':False,'network_acknowledged':True},{'model_id':'generation','license_acknowledged':True,'network_acknowledged':False},{'model_id':'generation','license_acknowledged':True,'network_acknowledged':True,'url':'https://attacker.invalid'}])
def test_download_requires_explicit_license_network_and_fixed_catalog(setup_client,body):
    assert setup_client.post('/api/setup/download',json=body).status_code==422
    assert setup_client.get('/api/setup').json()['runs']==[]


def test_browser_cannot_authorize_arbitrary_model_file_paths(setup_client,tmp_path):
    source=snapshot(tmp_path/'source')
    r=setup_client.post('/api/setup/import',json=dict(model_id='whisper-medium',source=str(source),license_acknowledged=True))
    assert r.status_code==403 and setup_client.get('/api/setup').json()['runs']==[]


def test_desktop_import_hashes_files_but_does_not_verify_inference(setup_client,tmp_path):
    c=setup_client;source=snapshot(tmp_path/'approved-snapshot-fixture')
    r=c.post('/api/setup/import',json=dict(model_id='whisper-medium',source=str(source),license_acknowledged=True),headers={'X-Desktop-Capability':'desktop-test-capability'})
    assert r.status_code==202
    result=finished(c,r.json()['id']);assert result['status']=='completed' and result['report']['files_installed']
    assert result['report']['inference_verified'] is False
    assert (c.app.state.setup.models/'whisper-medium/installation.json').is_file()
    verify=c.post('/api/setup/verify',json={'model_id':'whisper-medium'})
    assert finished(c,verify.json()['id'])['status']=='completed'
    (c.app.state.setup.models/'whisper-medium/model.bin').write_bytes(b'tampered fixture')
    verify=c.post('/api/setup/verify',json={'model_id':'whisper-medium'})
    assert finished(c,verify.json()['id'])['status']=='failed'


def test_snapshot_integrity_rejects_symlinks_traversal_and_unapproved_pipeline(tmp_path):
    source=snapshot(tmp_path/'snapshot');destination=tmp_path/'managed'
    install_snapshot('whisper-medium',source,destination)
    assert verify_snapshot('whisper-medium',destination)['license_acknowledged']
    manifest=json.loads((destination/'installation.json').read_text());manifest['sha256']['../outside']='a'*64
    (destination/'installation.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):verify_snapshot('whisper-medium',destination)
    (source/'config.json').unlink();(source/'config.json').symlink_to(source/'tokenizer.json')
    with pytest.raises(ValueError):validate_snapshot('whisper-medium',source)
    diar=tmp_path/'diar';diar.mkdir();(diar/'model.bin').write_bytes(b'fixture')
    (diar/'config.yaml').write_text('pipeline:\n  name: attacker.code.execute\n')
    with pytest.raises(ValueError):validate_snapshot('community-1',diar)


def test_installation_failure_never_persists_access_token_or_exception_text(setup_client):
    c=setup_client
    async def fail(*args):raise RuntimeError('hf_DO_NOT_RECORD_THIS_SECRET')
    c.app.state.setup.install=fail
    r=c.post('/api/setup/download',json=dict(model_id='community-1',license_acknowledged=True,network_acknowledged=True,access_token='hf_DO_NOT_RECORD_THIS_SECRET'))
    assert r.status_code==202 and finished(c,r.json()['id'])['status']=='failed'
    assert 'hf_DO_NOT_RECORD_THIS_SECRET' not in json.dumps(c.get('/api/setup').json())
    assert 'hf_DO_NOT_RECORD_THIS_SECRET' not in '\n'.join(c.app.state.store.db.iterdump())


def test_single_setup_job_cancel_and_session_admission(setup_client):
    c=setup_client;entered=False
    async def slow(*args):
        nonlocal entered;entered=True;await asyncio.sleep(30);return {}
    c.app.state.setup.install=slow
    r=c.post('/api/setup/download',json=dict(model_id='generation',license_acknowledged=True,network_acknowledged=True));rid=r.json()['id']
    assert c.post('/api/setup/self-test').status_code==409
    p=project(c);c.post(f'/api/projects/{p}/select')
    assert c.post('/api/sessions',json=dict(consent=True,project_id=p)).status_code==409
    assert c.post('/api/setup/cancel').status_code==200
    assert finished(c,rid)['status']=='cancelled' and not c.get('/api/state').json()['setup']['busy']
    assert c.post('/api/sessions',json=dict(consent=True,project_id=p)).status_code==201
    assert c.post('/api/setup/self-test').status_code==409


def test_real_offline_core_and_child_checks_do_not_pass_missing_model_tests(setup_client):
    c=setup_client;r=c.post('/api/setup/self-test');assert r.status_code==202
    row=finished(c,r.json()['id']);assert row['status']=='completed'
    checks={x['id']:x for x in row['report']['checks']}
    for id in ('storage','local_rag','question_guard','parser_worker'):assert checks[id]['status']=='passed'
    assert checks['asr_runtime']['status']=='blocked' and checks['diarization_runtime']['status']=='blocked'
    assert row['report']['all_passed'] is False
    assert c.app.state.store.db.execute('SELECT count(*) FROM generated_responses').fetchone()[0]==0


def test_finish_limited_mode_is_explicit_and_not_release_qualification(setup_client):
    c=setup_client
    assert c.post('/api/setup/finish',json=dict(privacy_acknowledged=True,sharing_acknowledged=True)).status_code==422
    assert c.post('/api/setup/finish',json=dict(privacy_acknowledged=False,sharing_acknowledged=True,allow_incomplete=True)).status_code==422
    r=c.post('/api/setup/finish',json=dict(privacy_acknowledged=True,sharing_acknowledged=True,allow_incomplete=True))
    assert r.status_code==200 and r.json()['completed']
    assert r.json()['acknowledgement']['limited'] and not r.json()['acknowledgement']['release_qualified']


def test_profile_cannot_be_applied_from_an_unmeasured_or_failed_run(setup_client):
    c=setup_client;r=c.post('/api/setup/self-test');row=finished(c,r.json()['id'])
    assert c.post('/api/setup/profiles/apply',json=dict(run_id=row['id'],accuracy_review_acknowledged=True)).status_code==422
    assert c.post('/api/setup/benchmark').status_code==409
    assert not c.get('/api/setup/live-check').json()['available']


def test_fixed_worker_dispatch_handles_bundled_mode_without_external_python(monkeypatch):
    assert command('document')[1:]==['-u','-m','pm_copilot.document_worker']
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    assert command('document')==[sys.executable,'--worker','document']
    with pytest.raises(ValueError):command('attacker_module')


def test_short_benchmark_records_live_evidence_and_requires_explicit_profile_review(tmp_path):
    class LiveMeeting(NoHardwareMeeting):
        def preflight(self,options):pass
        async def begin(self,sid,options,started_at):
            self.session_id=sid;self.state='capturing';self.asr_device='cpu';self.counts={'packets':1,'segments':0,'last_chunk_lag_ms':10,'local_audible_packets':1,'remote_audible_packets':1}
    gen=FixtureGeneration();app=create_app(tmp_path/'bench.sqlite3','test-secret','http://127.0.0.1:8750',meeting_factory=LiveMeeting,embedding_factory=NoModelEmbeddings,generation_factory=lambda:gen)
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:
        p=project(c);c.post(f'/api/projects/{p}/select');sid=c.post('/api/sessions',json=dict(project_id=p,consent=True,capture=True)).json()['session']['id']
        setup=app.state.setup;clock=[0.]
        setup.clock=lambda:clock[0]
        async def advance(seconds):clock[0]+=seconds
        setup.sleep=advance
        async def measured(messages,schema):
            clock[0]+=1
            app.state.meeting.counts['packets']+=1;app.state.meeting.counts['segments']+=2
            for language,text in [('en','Explicit English speech fixture'),('bg','Изричен български речеви тест')]:app.state.store.add_segment(sid,'remote',0,1,text,language,f'{clock[0]}-{language}')
            return json.dumps({'summary':'Idempotency prevents repeated side effects when an operation is retried. '*9}),dict(prompt_eval_count=500,eval_count=160)
        gen.generate=measured
        r=c.post('/api/setup/benchmark');assert r.status_code==202
        result=finished(c,r.json()['id']);assert result['status']=='completed' and result['report']['short_check_passed']
        assert len(result['report']['samples'])==3 and result['report']['languages_observed']==['bg','en']
        assert app.state.store.db.execute('SELECT count(*) FROM generated_responses').fetchone()[0]==0
        c.post(f'/api/sessions/{sid}/stop')
        assert c.post('/api/setup/profiles/apply',json=dict(run_id=r.json()['id'],accuracy_review_acknowledged=False)).status_code==422
        applied=c.post('/api/setup/profiles/apply',json=dict(run_id=r.json()['id'],accuracy_review_acknowledged=True))
        assert applied.status_code==200 and applied.json()['selected_profile']['accuracy_review_acknowledged']
        assert app.state.resources.settings.force_cpu and 'M7' in applied.json()['selected_profile']['qualification']


@pytest.mark.parametrize('mode',['success','cached','error','redirect'])
def test_approved_ollama_pull_protocol_and_no_repeated_download(setup_client,monkeypatch,mode):
    import httpx
    c=setup_client;original=httpx.AsyncClient;present=mode=='cached';pulls=[]
    def handle(request):
        nonlocal present
        assert request.url.host=='127.0.0.1' and request.url.port==11434
        if request.method=='GET':return httpx.Response(200,json={'models':[{'name':MODEL,'digest':'a'*64}] if present else []})
        assert request.url.path=='/api/pull' and json.loads(request.content)=={'model':MODEL,'stream':True}
        pulls.append(request)
        if mode=='redirect':return httpx.Response(307,headers={'Location':'https://attacker.invalid/model'})
        if mode=='error':return httpx.Response(200,content=b'{"error":"registry unavailable"}\n')
        present=True;return httpx.Response(200,content=b'{"status":"pulling manifest"}\n{"status":"success"}\n')
    def factory(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handle),**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',factory)
    r=c.post('/api/setup/download',json=dict(model_id='generation',license_acknowledged=True,network_acknowledged=True))
    assert r.status_code==202
    result=finished(c,r.json()['id'])
    assert result['status']==('completed' if mode in ('success','cached') else 'failed')
    if mode=='cached':assert not pulls and result['report']['already_present']
    else:assert len(pulls)==1


def test_snapshot_worker_pins_approved_revision_and_does_not_record_token(monkeypatch,tmp_path):
    import io
    from pm_copilot.asset_worker import main
    import huggingface_hub
    secret='hf_private_download_token';received=[]
    class Api:
        def __init__(self,token):assert token==secret
        def model_info(self,repository):
            assert repository=='Systran/faster-whisper-tiny';return SimpleNamespace(sha='a'*40)
    def download(**kwargs):
        received.append(kwargs);assert kwargs['repo_id']=='Systran/faster-whisper-tiny' and kwargs['revision']=='a'*40 and kwargs['token']==secret
        path=Path(kwargs['local_dir']);snapshot(path)
    monkeypatch.setattr(huggingface_hub,'HfApi',Api);monkeypatch.setattr(huggingface_hub,'snapshot_download',download)
    stage=tmp_path/'download';stage.mkdir();out=io.StringIO()
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps(dict(action='download',model_id='whisper-tiny',destination=str(tmp_path/'model'),temporary_root=str(stage),access_token=secret))))
    monkeypatch.setattr(sys,'stdout',out);monkeypatch.setattr(sys,'stderr',io.StringIO())
    assert main()==0
    assert json.loads(out.getvalue())['result']['revision']=='a'*40
    assert secret not in out.getvalue() and secret not in (tmp_path/'model/installation.json').read_text()
    assert len(received)==1 and list(stage.iterdir())==[]


def test_interrupted_model_replacement_restores_previous_snapshot(tmp_path):
    from pm_copilot.model_assets import recover_installations
    source=snapshot(tmp_path/'source');root=tmp_path/'models';root.mkdir()
    destination=root/'whisper-medium';install_snapshot('whisper-medium',source,destination)
    destination.rename(root/'whisper-medium.previous');(root/'whisper-medium.installing').mkdir()
    from uuid import uuid4
    stage=root/'.downloads'/str(uuid4());stage.mkdir(parents=True);(stage/'partial.bin').write_bytes(b'fixture')
    keep=root/'.downloads'/'user-folder';keep.mkdir()
    recover_installations(root)
    assert verify_snapshot('whisper-medium',destination)['license_acknowledged']
    assert not stage.exists() and not (root/'whisper-medium.installing').exists() and keep.exists()


@pytest.mark.parametrize('action',['pause','stop','manual'])
def test_live_controls_and_manual_questions_preempt_setup_benchmark(setup_client,action):
    c=setup_client;p=project(c);c.post(f'/api/projects/{p}/select');sid=c.post('/api/sessions',json=dict(project_id=p,consent=True)).json()['session']['id']
    c.app.state.meeting.state='capturing';c.app.state.meeting.session_id=sid
    async def slow():await asyncio.sleep(30);return {'short_check_passed':True}
    c.app.state.setup.benchmark=slow
    r=c.post('/api/setup/benchmark');rid=r.json()['id'];assert r.status_code==202
    if action=='manual':
        c.app.state.assistance.generator=FixtureGeneration()
        c.app.state.store.add_segment(sid,'remote',0,1,'How can retries avoid duplicates?','en','manual')
        from datetime import datetime
        start=datetime.fromisoformat(c.app.state.store.require_session(p,sid)['started_at']).timestamp()
        c.app.state.assistance.clock=lambda:start+2
        manual=c.post(f'/api/projects/{p}/sessions/{sid}/assistance',json={})
        from test_assistance import finished as assistance_finished
        assistance_finished(c,f'/api/projects/{p}/sessions/{sid}/assistance',manual.json()['id'],'completed')
    else:assert c.post(f'/api/sessions/{sid}/{action}').status_code==200
    assert finished(c,rid)['status']=='cancelled' and not c.get('/api/setup').json()['busy']


def test_cancelling_setup_before_its_task_starts_releases_all_flags(setup_client):
    setup=setup_client.app.state.setup
    async def immediate():
        row=await setup.start('self_test');await setup.cancel();return setup.run(row['id'])
    row=setup_client.portal.call(immediate)
    assert row['status']=='cancelled' and not setup.active and setup.phase=='idle'
    assert not setup.documents.manual_active and not setup.resources.manual_pending
