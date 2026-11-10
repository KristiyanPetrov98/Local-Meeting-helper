from typing import Any
from pydantic import BaseModel,ConfigDict,Field
from fastapi import Response
from .resources import ResourceSettings
from .sharing import SharingChoice
from .store import DomainError

class Window(BaseModel):
    id:str
    hwnd:int
    pid:int
    title:str
    project_id:str | None=None

class ScreenState(BaseModel):
    available:bool
    reason:str | None
    state:str
    error:str | None
    selected:Window | None
    project_id:str | None
    session_id:str | None
    counts:dict[str,int]
    risks_enabled:bool
    risk_count:int
    risks:list[dict[str,Any]]
    observation_available:bool
    preview_available:bool
    analysis_deferred:bool

class SharingState(SharingChoice):
    mini_allowed:bool
    capture_exclusion_verified:bool
    meet_picker_enforced:bool

class ResourceState(BaseModel):
    gpus:list[dict[str,Any]]
    resident:list[dict[str,Any]]
    reason:str | None
    settings:ResourceSettings
    active_job:str | None
    profile:str | None
    manual_pending:bool
    samples_age_ms:int | None
    budget_is_estimate:bool
    events:list[dict[str,Any]]

class WindowChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_id:str | None=Field(default=None,max_length=100)


def register_m5_routes(app,store,screen,resources,sharing,change,lifecycle_lock):
    @app.get('/api/sharing',response_model=SharingState)
    async def sharing_status():return sharing.status()

    @app.put('/api/sharing',response_model=SharingState)
    async def sharing_update(body:SharingChoice):
        async with lifecycle_lock:
            sharing.update(body)
            if not sharing.status()['mini_allowed']:
                screen.paused_capture=False;screen.paused_risks=False
                await screen.stop()
            await change(store.bump)
            return sharing.status()

    @app.get('/api/resources',response_model=ResourceState)
    async def resource_status():return await resources.refresh()

    @app.put('/api/resources/settings',response_model=ResourceState)
    async def resource_settings(body:ResourceSettings):
        if resources.active_task:raise DomainError('Wait for inference to finish before changing resource settings')
        resources.settings=body
        await change(store.setting,'resource_settings',body.model_dump_json())
        await change(store.bump)
        return resources.status()

    @app.get('/api/screen/windows',response_model=list[Window])
    async def windows():return await screen.native.windows()

    @app.get('/api/screen',response_model=ScreenState)
    async def screen_status():return screen.status()

    @app.put('/api/projects/{project_id}/screen',response_model=ScreenState)
    async def selection(project_id:str,body:WindowChoice):
        async with lifecycle_lock:await screen.select(project_id,body.source_id)
        return screen.status()

    @app.get('/api/projects/{project_id}/sessions/{session_id}/screen/preview')
    async def preview(project_id:str,session_id:str):
        store.require_session(project_id,session_id)
        if screen.pid!=project_id or screen.sid!=session_id:raise DomainError('No preview in this project/session',404)
        return Response(screen.preview(),media_type='image/png',headers={'Cache-Control':'no-store'})
