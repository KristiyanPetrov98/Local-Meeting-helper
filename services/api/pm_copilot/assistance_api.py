from uuid import UUID,uuid4
from pydantic import BaseModel,Field,ConfigDict
from .briefing import Briefing
from .document_api import Citation

class TriggerAssistance(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:UUID=Field(default_factory=uuid4)

class AssistanceState(BaseModel):
    busy:bool
    active_request_id:str | None
    phase:str

class AssistanceDiagnostics(BaseModel):
    available:bool
    model:str
    digest:str | None
    context:int
    screen_available:bool
    reason:str | None

class AssistanceSummary(BaseModel):
    id:str
    project_id:str
    session_id:str
    status:str
    phase:str
    created_at:str
    completed_at:str | None
    window_start:float
    window_end:float
    transcript_digest:str
    question:str | None
    segment_ids:list[int]
    error:str | None
    warnings:list[str]
    elapsed_ms:int | None

class SavedBriefing(BaseModel):
    id:str
    body:Briefing
    model:str
    model_digest:str
    metrics:dict[str,int | None]

class AssistanceDetail(AssistanceSummary):
    response:SavedBriefing | None
    citations:list[Citation]
    unavailable_citations:list[str]


def register_assistance_routes(app,store,assistance,lifecycle_lock):
    @app.get('/api/assistance/status',response_model=AssistanceDiagnostics)
    async def status():return await assistance.diagnostics()

    @app.post('/api/projects/{project_id}/sessions/{session_id}/assistance',response_model=AssistanceDetail,status_code=202)
    async def trigger(project_id:str,session_id:str,body:TriggerAssistance):
        async with lifecycle_lock:
            return await assistance.trigger(project_id,session_id,str(body.request_id))

    @app.get('/api/projects/{project_id}/sessions/{session_id}/assistance',response_model=list[AssistanceSummary])
    async def history(project_id:str,session_id:str):
        store.require_session(project_id,session_id)
        ids=store.db.execute('SELECT id FROM assistance_requests WHERE project_id=? AND session_id=? ORDER BY created_at DESC LIMIT 30',(project_id,session_id)).fetchall()
        return [store.request_row(project_id,session_id,r['id']) for r in ids]

    @app.get('/api/projects/{project_id}/sessions/{session_id}/assistance/{request_id}',response_model=AssistanceDetail)
    async def detail(project_id:str,session_id:str,request_id:str):
        return store.assistance_detail(project_id,session_id,request_id)

    @app.post('/api/projects/{project_id}/sessions/{session_id}/assistance/{request_id}/cancel',response_model=AssistanceDetail)
    async def cancel(project_id:str,session_id:str,request_id:str):
        async with lifecycle_lock:
            return await assistance.cancel(project_id,session_id,request_id)
