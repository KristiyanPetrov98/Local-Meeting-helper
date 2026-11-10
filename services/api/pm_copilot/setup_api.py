from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field,SecretStr
from fastapi import Request
from .store import DomainError
from .security import token_matches

ModelId=Literal['generation','embedding','whisper-medium','whisper-small','whisper-tiny','community-1']
SnapshotId=Literal['whisper-medium','whisper-small','whisper-tiny','community-1']

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')

class SetupSummary(BaseModel):
    completed:bool
    active_run_id:str | None
    phase:str
    busy:bool

class SetupConfiguration(Strict):
    asr_size:Literal['medium','small','tiny']='medium'
    asr_device:Literal['cpu','cuda']='cpu'
    force_cpu:bool=False
    reserve_mib:int=Field(default=2048,ge=1024,le=8192)
    generation_budget_mib:int=Field(default=8192,ge=4096,le=16384)

class SetupDownload(Strict):
    model_id:ModelId
    license_acknowledged:bool
    network_acknowledged:bool
    replace:bool=False
    access_token:SecretStr | None=Field(default=None,max_length=300)

class SetupImport(Strict):
    model_id:SnapshotId
    source:str=Field(min_length=1,max_length=4096)
    license_acknowledged:bool
    replace:bool=False

class SetupVerify(Strict):model_id:SnapshotId

class Prepare(Strict):
    license_acknowledged:bool
    network_acknowledged:bool

class SetupApplyProfile(Strict):
    run_id:str=Field(max_length=100)
    accuracy_review_acknowledged:bool

class SetupFinish(Strict):
    privacy_acknowledged:bool
    sharing_acknowledged:bool
    allow_incomplete:bool=False

class SetupRun(BaseModel):
    id:str
    kind:str
    status:str
    created_at:str
    completed_at:str | None
    report:dict[str,Any]

class SetupStatus(SetupSummary):
    preferences:dict[str,Any]
    acknowledgement:dict[str,Any] | None
    assets:list[dict[str,Any]]
    runs:list[SetupRun]
    selected_profile:dict[str,Any] | None


def register_setup_routes(app,setup,lifecycle_lock):
    @app.post('/api/setup/prepare',response_model=SetupRun,status_code=202)
    async def prepare(body:Prepare):
        if not body.license_acknowledged or not body.network_acknowledged:raise DomainError('Review the model licenses and allow the one-time downloads first',422)
        async with lifecycle_lock:return await setup.start('prepare')

    @app.get('/api/setup',response_model=SetupStatus)
    async def status():return setup.status()

    @app.get('/api/setup/diagnostics',response_model=dict[str,Any])
    async def diagnostics():return await setup.diagnostics()

    @app.put('/api/setup/configuration',response_model=SetupStatus)
    async def configure(body:SetupConfiguration):
        async with lifecycle_lock:return await setup.configure(body)

    @app.post('/api/setup/download',response_model=SetupRun,status_code=202)
    async def download(body:SetupDownload):
        if not body.license_acknowledged or not body.network_acknowledged:raise DomainError('Explicit license/access and one-time network acknowledgement are required',422)
        async with lifecycle_lock:
            params=body.model_dump(exclude={'access_token'})
            if body.access_token:params['access_token']=body.access_token.get_secret_value()
            return await setup.start('download',params)

    @app.post('/api/setup/import',response_model=SetupRun,status_code=202)
    async def import_snapshot(body:SetupImport,request:Request):
        capability=request.headers.get('x-desktop-capability','')
        if not setup.desktop_capability or not token_matches(capability,setup.desktop_capability):raise DomainError('Use the desktop folder picker to authorize a local model import',403)
        if not body.license_acknowledged:raise DomainError('Acknowledge the official snapshot source and license first',422)
        async with lifecycle_lock:return await setup.start('import',body.model_dump())

    @app.post('/api/setup/verify',response_model=SetupRun,status_code=202)
    async def verify(body:SetupVerify):
        async with lifecycle_lock:return await setup.start('verify',body.model_dump())

    @app.post('/api/setup/self-test',response_model=SetupRun,status_code=202)
    async def self_test():
        async with lifecycle_lock:return await setup.start('self_test')

    @app.post('/api/setup/benchmark',response_model=SetupRun,status_code=202)
    async def benchmark():
        async with lifecycle_lock:return await setup.start('benchmark')

    @app.post('/api/setup/profiles/apply',response_model=SetupStatus)
    async def profile(body:SetupApplyProfile):
        async with lifecycle_lock:return await setup.apply_profile(body.run_id,body.accuracy_review_acknowledged)

    @app.get('/api/setup/live-check',response_model=dict[str,Any])
    async def live():return setup.live_check()

    @app.post('/api/setup/cancel',response_model=SetupStatus)
    async def cancel():
        async with lifecycle_lock:return await setup.cancel()

    @app.post('/api/setup/finish',response_model=SetupStatus)
    async def finish(body:SetupFinish):
        async with lifecycle_lock:return await setup.acknowledge(body.privacy_acknowledged,body.sharing_acknowledged,body.allow_incomplete)
