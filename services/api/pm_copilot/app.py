import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import Store, DomainError
from .meeting import Meeting, AudioOptions
from .documents import Documents
from .document_api import register_document_routes
from .resources import Resources,ResourceSettings
from .sharing import Sharing
from .screen import Screen
from .screen_native import NativeScreen
from .m5_api import register_m5_routes,ScreenState,SharingState,ResourceState
from .onboarding import Onboarding
from .setup_api import register_setup_routes,SetupSummary
from .assistance import Assistance
from .assistance_api import register_assistance_routes, AssistanceState
from .security import RequestSizeLimit, token_matches
from .qualification import Qualification, register_qualification_routes


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProjectName(StrictModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator('name')
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value or any(ord(c)<32 for c in value):
            raise ValueError('Use a nonempty project name without control characters')
        return value


class Start(StrictModel):
    consent: bool
    project_id: str
    capture: bool = False
    screen: bool = False
    risks: bool = False


class Shortcut(StrictModel):
    accelerator: str = Field(pattern=r'^(Control|Alt|Shift|Super)(\+(Control|Alt|Shift|Super))*\+([A-Z0-9]|Space|F[1-9]|F1[0-9]|F2[0-4])$')


class Project(BaseModel):
    id: str
    name: str
    created_at: str


class Session(BaseModel):
    id: str
    project_id: str
    state: Literal['active','paused','stopped','interrupted']
    started_at: str
    ended_at: str | None
    consent: bool


class Capabilities(BaseModel):
    audio_capture: bool
    assistance: bool


class Snapshot(BaseModel):
    revision: int
    projects: list[Project]
    selected_project_id: str | None
    session: Session | None
    sessions: list[Session]
    shortcut: str
    capabilities: Capabilities
    meeting: "MeetingStatus"
    assistance: AssistanceState
    screen: ScreenState
    sharing: SharingState
    resources: ResourceState
    setup: SetupSummary


class MeetingStatus(BaseModel):
    available: bool
    reason: str | None
    process_loopback: bool
    diarization_model_present: bool
    state: str
    error: str | None
    session_id: str | None
    counts: dict[str, int]
    queue_depth: int


class MergeSpeaker(StrictModel):
    target: str


class Retention(StrictModel):
    days: int = Field(ge=1, le=3650)


class TranscriptSegment(BaseModel):
    id: int
    session_id: str
    source: Literal['local','remote']
    start: float
    end: float
    text: str
    language: str
    speaker_id: str
    segment_key: str
    created_at: str


class Speaker(BaseModel):
    id: str
    name: str


class TranscriptPage(BaseModel):
    segments: list[TranscriptSegment]
    speakers: list[Speaker]
    older_cursor: int | None


def create_app(database, token, origin, web_dir=None, meeting_factory=Meeting, embedding_factory=None, generation_factory=None, assistance_clock=None, assistance_deadline=60, resource_probe=None, screen_native_factory=None, observation_factory=None, excluded_pids=(), desktop_capability=None):
    store = Store(database)
    listeners = set()
    lock = asyncio.Lock()
    lifecycle_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app):
        async def retention_loop():
            while True:
                await asyncio.sleep(600)
                await change(store.purge_transcripts)
        maintenance = asyncio.create_task(retention_loop())
        documents.start()
        resources.start()
        try:
            yield
        finally:
            maintenance.cancel()
            await asyncio.gather(maintenance, return_exceptions=True)
            await qualification.close()
            await setup.close()
            await assistance.close()
            await screen.stop()
            await resources.close()
            await documents.close()
            await meeting.stop(flush=False)
            store.close()

    app = FastAPI(title='PM Copilot Local API', version='0.1.0', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    base_openapi = app.openapi
    def authenticated_schema():
        schema = base_openapi()
        schema.setdefault('components', {}).setdefault('securitySchemes', {})['LocalBearer'] = {'type':'http','scheme':'bearer'}
        for path, methods in schema['paths'].items():
            if path.startswith('/api/'):
                for operation in methods.values():
                    operation['security'] = [{'LocalBearer': []}]
        return schema
    app.openapi = authenticated_schema

    app.add_middleware(RequestSizeLimit)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        if request.headers.get('host') != origin.removeprefix('http://') or request.headers.get('origin', origin) != origin:
            response = JSONResponse({'detail':'Host or origin rejected'}, status_code=403)
        elif request.url.path.startswith('/api/') and not token_matches(request.headers.get('authorization', ''), 'Bearer '+token):
            response = JSONResponse({'detail':'Authentication required'}, status_code=401)
        else:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' {origin.replace('http:', 'ws:')}; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({'detail':exc.message}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default response includes raw input, including failed token
        # fields and an entire body on malformed JSON. Return locations only.
        return JSONResponse({'detail': [{'type': e['type'], 'loc': list(e['loc'])[:8],
                                         'msg': 'Invalid request value'} for e in exc.errors()][:20]}, status_code=422)

    def view():
        snapshot = store.snapshot()
        snapshot['meeting'] = meeting.status()
        snapshot['assistance']=assistance.status()
        snapshot['screen']=screen.status();snapshot['sharing']=sharing.status();snapshot['resources']=resources.status();snapshot['setup']=setup.summary()
        snapshot['capabilities']['assistance']=True
        snapshot['capabilities']['audio_capture'] = snapshot['meeting']['available']
        return snapshot

    async def change(fn, *args):
        async with lock:
            with store.db:
                fn(*args)
            snapshot = view()
            for q in listeners:
                if q.full():
                    q.get_nowait()
                q.put_nowait(snapshot)
            return snapshot

    async def notify():
        await change(store.bump)

    async def segment(*args):
        await change(store.add_segment, *args)

    async def refine(*args):
        await change(store.refine_speakers, *args)

    meeting = meeting_factory(notify, segment, refine)
    app.state.meeting = meeting
    documents = Documents(store,change,embedding_factory() if embedding_factory else None)
    app.state.documents = documents
    register_document_routes(app,store,documents,change)
    assistance=Assistance(store,change,documents,generation_factory() if generation_factory else None,assistance_clock,assistance_deadline)
    sharing=Sharing()
    resources=Resources(notify,meeting,resource_probe,ResourceSettings.model_validate_json(store.value('resource_settings','{}')))
    screen=Screen(store,notify,documents,resources,sharing,screen_native_factory() if screen_native_factory else NativeScreen(excluded_pids),observation_factory() if observation_factory else None)
    assistance.scheduler=resources;assistance.screen=screen
    meeting.optional_busy=lambda:resources.manual_pending
    app.state.resources=resources;app.state.screen=screen;app.state.sharing=sharing
    qualification=Qualification(store,meeting,resources,assistance)
    app.state.qualification=qualification
    register_qualification_routes(app,qualification,lifecycle_lock)
    setup=Onboarding(store,change,meeting,documents,assistance,screen,resources,Path(database).parent,desktop_capability)
    assistance.before_manual=setup.interrupt_benchmark
    app.state.setup=setup
    app.state.assistance=assistance
    register_assistance_routes(app,store,assistance,lifecycle_lock)
    register_m5_routes(app,store,screen,resources,sharing,change,lifecycle_lock)
    register_setup_routes(app,setup,lifecycle_lock)

    def options():
        return AudioOptions.model_validate_json(store.value('audio_options', AudioOptions().model_dump_json()))

    @app.get('/api/audio/devices')
    async def devices():
        return await meeting.enumerate_devices()

    @app.get('/api/audio/settings', response_model=AudioOptions)
    async def audio_settings():
        return options()

    @app.put('/api/audio/settings', response_model=Snapshot)
    async def audio_settings_update(body: AudioOptions):
        async with lifecycle_lock:
            if store.live() and store.live()['state'] != 'paused':
                raise DomainError('Pause or stop the session before changing audio settings')
            if not body.microphone and not body.loopback:
                raise DomainError('Select at least one audio source',422)
            await change(store.setting, 'audio_options', body.model_dump_json())
            return await change(store.bump)

    @app.post('/api/audio/retry', response_model=Snapshot)
    async def retry_capture():
        async with lifecycle_lock:
            live = store.live()
            if not live or live['state'] != 'active':
                raise DomainError('An active session is required')
            selected = options(); meeting.preflight(selected)
            await meeting.begin(live['id'], selected, live['started_at'])
            return view()

    @app.get('/api/settings/retention', response_model=Retention)
    async def retention():
        return {'days':int(store.value('retention_days','30'))}

    @app.put('/api/settings/retention', response_model=Snapshot)
    async def set_retention(body: Retention):
        await change(store.setting,'retention_days',str(body.days))
        return await change(store.purge_transcripts)

    @app.get('/api/projects/{project_id}/sessions/{session_id}/transcript', response_model=TranscriptPage)
    async def transcript(project_id: str, session_id: str, before: int | None = None):
        return store.transcript(project_id,session_id,before)

    @app.patch('/api/projects/{project_id}/sessions/{session_id}/speakers/{speaker_id}', response_model=Snapshot)
    async def rename_speaker(project_id: str, session_id: str, speaker_id: str, body: ProjectName):
        return await change(store.rename_speaker,project_id,session_id,speaker_id,body.name)

    @app.post('/api/projects/{project_id}/sessions/{session_id}/speakers/{speaker_id}/merge', response_model=Snapshot)
    async def merge_speaker(project_id: str, session_id: str, speaker_id: str, body: MergeSpeaker):
        return await change(store.merge_speakers,project_id,session_id,speaker_id,body.target)

    @app.get('/api/state', response_model=Snapshot)
    async def state():
        return view()

    @app.get('/api/schema')
    async def schema():
        return app.openapi()

    @app.post('/api/projects', response_model=Snapshot, status_code=201)
    async def create(body: ProjectName):
        return await change(store.create, body.name)

    @app.patch('/api/projects/{project_id}', response_model=Snapshot)
    async def rename(project_id: str, body: ProjectName):
        return await change(store.rename, project_id, body.name)

    @app.delete('/api/projects/{project_id}', response_model=Snapshot)
    async def delete(project_id: str):
        async with lifecycle_lock:
            result=await change(store.delete,project_id)
            if screen.selected and screen.selected['project_id']==project_id:await screen.stop(clear_selection=True);result=await change(store.bump)
            return result

    @app.post('/api/projects/{project_id}/select', response_model=Snapshot)
    async def select(project_id: str):
        async with lifecycle_lock:
            result=await change(store.select,project_id)
            if screen.selected and screen.selected['project_id']!=project_id:await screen.stop(clear_selection=True);result=await change(store.bump)
            return result

    @app.post('/api/sessions', response_model=Snapshot, status_code=201)
    async def start(body: Start):
        async with lifecycle_lock:
            if setup.active:raise DomainError('Finish or cancel setup operations before starting a session')
            selected = options()
            screen.preflight(body.project_id,body.screen)
            if body.capture: meeting.preflight(selected)
            await change(store.start, body.project_id, body.consent)
            live = store.live()
            if body.capture:
                await meeting.begin(live['id'], selected, live['started_at'])
            await screen.begin(body.project_id,live['id'],body.screen,body.risks)
            return view()

    @app.post('/api/sessions/{session_id}/{action}', response_model=Snapshot)
    async def transition(session_id: str, action: Literal['pause','resume','stop']):
        async with lifecycle_lock:
            live = store.live()
            if not live or live['id'] != session_id:
                raise DomainError('Session is no longer active')
            if action == 'resume' and live['state'] != 'paused' or action == 'pause' and live['state'] != 'active':
                raise DomainError('Invalid session transition')
            was_screen=screen.state in ('capturing','starting');was_risks=screen.risks_enabled
            if action=='resume':
                was_screen=bool(getattr(screen,'paused_capture',False));was_risks=bool(getattr(screen,'paused_risks',False))
            was_capture = meeting.session_id == session_id
            if action == 'resume':
                if was_capture:meeting.preflight(options())
                screen.preflight(live['project_id'],was_screen)
            if action in ('pause','stop'):
                await setup.interrupt_benchmark()
                await assistance.cancel_session(session_id)
                screen.paused_capture=was_screen if action=='pause' else False;screen.paused_risks=was_risks if action=='pause' else False
                await screen.stop()
                await meeting.stop()
            await change(store.transition, session_id, action)
            if action == 'resume' and was_capture:
                await meeting.begin(session_id, options(), live['started_at'])
            if action=='resume':
                await screen.begin(live['project_id'],session_id,was_screen,was_risks)
            return view()

    @app.put('/api/settings/shortcut', response_model=Snapshot)
    async def shortcut(body: Shortcut):
        return await change(store.shortcut, body.accelerator)

    @app.websocket('/api/events')
    async def events(ws: WebSocket):
        if ws.headers.get('host') != origin.removeprefix('http://') or ws.headers.get('origin') != origin:
            await ws.close(code=1008)
            return
        await ws.accept()
        q = asyncio.Queue(maxsize=1)
        try:
            message = await asyncio.wait_for(ws.receive(), 5)
            auth = message.get('text')
            try: credentials = json.loads(auth) if isinstance(auth, str) and len(auth.encode()) <= 512 else None
            except ValueError: credentials = None
            if not isinstance(credentials, dict) or not token_matches(credentials.get('token'), token):
                await ws.close(code=1008)
                return
            async with lock:
                listeners.add(q)
                q.put_nowait(view())
            async def send():
                while True:
                    await ws.send_json({'type':'state.updated','version':1,'state':await q.get()})
            async def receive():
                while True:
                    # No client commands over event channel; detect close promptly.
                    message = await ws.receive()
                    if message['type'] == 'websocket.disconnect': return
                    await ws.close(code=1008)
                    return
            tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        # A closing ASGI connection can cancel the handler while its sender/receiver
        # tasks are draining. Treat that cancellation as an ordinary disconnect.
        except (WebSocketDisconnect, asyncio.CancelledError, asyncio.TimeoutError, ValueError, TypeError, AttributeError):
            pass
        finally:
            listeners.discard(q)

    if web_dir:
        web_dir = Path(web_dir)
        app.mount('/assets', StaticFiles(directory=web_dir/'assets'), name='assets')
        @app.get('/')
        async def index():
            return FileResponse(web_dir/'index.html')
    return app
