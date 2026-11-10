import asyncio
import json
import time
from .briefing import MODEL,CONTEXT,build_prompt,validate_briefing,BriefingInvalid
from .generation import OllamaGeneration,GenerationUnavailable
from .questions import latest_question
from .store import DomainError
from contextlib import asynccontextmanager
from .resources import ResourceDeferred


class Assistance:
    def __init__(self,store,change,documents,generator=None,clock=None,deadline=60):
        self.store,self.change,self.documents=store,change,documents
        self.scheduler=None;self.screen=None;self.before_manual=None
        self.generator=generator or OllamaGeneration();self.clock=clock or time.time;self.deadline=deadline
        self.task=None;self.active=None;self.phase='idle';self.trigger_lock=asyncio.Lock();self.started=0.

    def status(self):return {'busy':bool(self.active),'active_request_id':self.active,'phase':self.phase}

    async def diagnostics(self):
        import importlib.util
        if importlib.util.find_spec('langdetect') is None:
            return {'available':False,'model':MODEL,'digest':None,'context':CONTEXT,'screen_available':bool(self.screen and self.screen.status()['observation_available']),'reason':'Install requirements-assistance.lock for output validation'}
        try:digest=await self.generator.identity()
        except GenerationUnavailable as exc:return {'available':False,'model':MODEL,'digest':None,'context':CONTEXT,'screen_available':bool(self.screen and self.screen.status()['observation_available']),'reason':str(exc)}
        return {'available':True,'model':MODEL,'digest':digest,'context':CONTEXT,'screen_available':bool(self.screen and self.screen.status()['observation_available']),'reason':None}

    async def trigger(self,project_id,session_id,request_id):
        async with self.trigger_lock:
            session=self.store.require_session(project_id,session_id)
            existing=self.store.db.execute('SELECT project_id,session_id FROM assistance_requests WHERE id=?',(request_id,)).fetchone()
            if existing:
                if existing['project_id']!=project_id or existing['session_id']!=session_id:raise DomainError('Request ID already belongs to another scope',409)
                return self.store.assistance_detail(project_id,session_id,request_id)
            if session['state'] not in ('active','paused') or self.store.value('selected_project_id')!=project_id:raise DomainError('Select this project and start a session before requesting assistance')
            if self.active:raise DomainError('A briefing request is already running; there is no queued generation')
            start,end,rows,digest=self.store.snapshot_window(project_id,session_id,self.clock())
            if len(rows)>500 or sum(len(r['text']) for r in rows)>64000:raise DomainError('Confirmed transcript window exceeds the bounded assistance limit',422)
            question=latest_question(rows)
            screen_context=self.screen.context(project_id,session_id) if self.screen else None
            warnings=['Recent selected-window observation included as unverified context.'] if screen_context else ['Screen context is unavailable: capture is off, stale, or has no validated observation.']
            if rows and end-max(r['end'] for r in rows)>5:warnings.append('The latest confirmed transcript is over five seconds behind the trigger time.')
            if question:
                self.active=request_id;self.phase='retrieving';self.started=time.monotonic();self.documents.manual_active=True
            try:await self.change(self.store.record_assistance,request_id,project_id,session_id,start,end,digest,question,warnings)
            except BaseException:
                if self.active==request_id:self.active=None;self.phase='idle';self.documents.manual_active=False
                raise
            if question:
                self.task=asyncio.create_task(self._run(project_id,session_id,request_id,question,rows,warnings,screen_context))
            return self.store.assistance_detail(project_id,session_id,request_id)

    async def _phase(self,request_id,phase):
        self.phase=phase;await self.change(self.store.assistance_phase,request_id,phase)

    async def _run(self,pid,sid,rid,question,rows,warnings,screen_context=None):
        try:
            async with asyncio.timeout(self.deadline):
                if self.before_manual:await self.before_manual()
                if self.scheduler:await self.scheduler.begin_manual()
                project=self.store.project(pid)
                retrieved=await self.documents.search(pid,question.text,'hybrid')
                if retrieved['warning']:warnings.append(retrieved['warning'])
                citations=[hit['citation'] for hit in retrieved['hits']]
                # Include a preferred newer source when structured conflict detection found one.
                for conflict in reversed(retrieved['conflicts'][:2]):
                    cid=conflict['preferred_citation_id']
                    if cid not in {c['citation_id'] for c in citations[:1]}:
                        citations=[self.store.citation(pid,cid)]+[c for c in citations if c['citation_id']!=cid]
                if retrieved['conflicts']:warnings.append('Conflicting document values were retrieved; review the source dates and evidence.')
                messages,schema,shown,trimmed,byte_count=build_prompt(question,rows,citations,project['name'],screen_context)
                warnings.extend(trimmed)
                allowed={c['citation_id'] for c in shown}
                await self._phase(rid,'generating')
                # The same lock serializes this heavy request against local embedding calls.
                async with self._lease() as profile:
                    if profile=='cpu':warnings.append('GPU budget/reserve unavailable or CPU selected; primary 8B inference uses CPU with four threads.')
                    async with self.documents.embed_lock:
                        digest=await self.generator.identity()
                        content,metrics=await self.generator.generate(messages,schema)
                        if await self.generator.identity()!=digest:raise BriefingInvalid('Generation model changed during the request')
                await self._phase(rid,'validating')
                try:payload=json.loads(content)
                except (ValueError,TypeError) as exc:raise BriefingInvalid('Model did not return a JSON briefing') from exc
                body=await asyncio.to_thread(validate_briefing,payload,allowed,question.text,project['name'])
                used=set(cid for claim in [body['briefing'],*body['supporting_points']] for cid in claim['citation_ids'])
                for cid in used:
                    cite=self.store.citation(pid,cid)
                    if cite['superseded']:raise BriefingInvalid('A source changed during generation; request a new briefing')
                session=self.store.require_session(pid,sid)
                if session['state'] not in ('active','paused') or self.store.value('selected_project_id')!=pid:raise BriefingInvalid('Session or project changed during generation')
                metrics={**metrics,'input_bytes_including_schema':byte_count}
                def save():
                    self.store.save_response(rid,body,self.generator.model,digest,metrics)
                    self.store.finish_assistance(rid,'completed',None,self._elapsed(),warnings)
                await self.change(save)
        except asyncio.CancelledError:
            await self.change(self.store.finish_assistance,rid,'cancelled','Request cancelled',self._elapsed())
            raise
        except TimeoutError:
            await self.change(self.store.finish_assistance,rid,'error','Assistance exceeded the 60-second deadline; capture was not stopped',self._elapsed())
        except (GenerationUnavailable,BriefingInvalid,DomainError,ResourceDeferred) as exc:
            detail=exc.message if isinstance(exc,DomainError) else str(exc)
            await self.change(self.store.finish_assistance,rid,'error',detail,self._elapsed())
        except Exception:
            await self.change(self.store.finish_assistance,rid,'error','Local assistance failed validation; no answer was saved',self._elapsed())
        finally:
            if self.active==rid:
                if self.scheduler:self.scheduler.end_manual()
                self.active=None;self.phase='idle';self.documents.manual_active=False
                await self.change(self.store.bump)

    @asynccontextmanager
    async def _lease(self):
        if self.scheduler:
            async with self.scheduler.lease('manual') as profile:
                yield profile
        else:yield None

    def _elapsed(self):return round((time.monotonic()-self.started)*1000)

    async def cancel(self,project_id,session_id,request_id):
        row=self.store.request_row(project_id,session_id,request_id)
        if self.active==request_id:
            if self.task:
                self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
            if self.store.request_row(project_id,session_id,request_id)['status'] in ('retrieving','generating','validating'):
                await self.change(self.store.finish_assistance,request_id,'cancelled','Request cancelled',self._elapsed())
            if self.active==request_id:
                if self.scheduler:self.scheduler.end_manual()
                self.active=None;self.phase='idle';self.documents.manual_active=False
                await self.change(self.store.bump)
        return self.store.assistance_detail(project_id,session_id,request_id)

    async def cancel_session(self,session_id):
        if self.active:
            row=self.store.db.execute('SELECT project_id,session_id FROM assistance_requests WHERE id=?',(self.active,)).fetchone()
            if row and row['session_id']==session_id:await self.cancel(row['project_id'],session_id,self.active)

    async def close(self):
        if self.active:
            row=self.store.db.execute('SELECT project_id,session_id FROM assistance_requests WHERE id=?',(self.active,)).fetchone()
            if row:await self.cancel(row['project_id'],row['session_id'],self.active)
