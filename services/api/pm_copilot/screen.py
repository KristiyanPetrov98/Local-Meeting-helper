"""Ephemeral selected-window capture and low-priority risk observations."""
import asyncio
import hashlib
import time
from .briefing import BriefingInvalid
from .generation import OllamaGeneration,GenerationUnavailable
from .resources import ResourceDeferred
from .screen_native import NativeScreen
from .visual import Changes,decode_frame,difference,analysis_prompt,validate_observation
from .store import DomainError

class Screen:
    def __init__(self,store,notify,documents,resources,sharing,native=None,generator=None,clock=None):
        self.store,self.notify,self.documents,self.resources,self.sharing=store,notify,documents,resources,sharing
        self.native=native or NativeScreen();self.generator=generator or OllamaGeneration();self.clock=clock or time.monotonic
        self.selected=None;self.pid=self.sid=None;self.capture_task=self.worker=self.job=None
        self.state='idle';self.error=None;self.frame=None;self.observation=None;self.risks=[]
        self.changes=Changes();self.risks_enabled=False;self.last_text_digest=None;self.last_analysis=-float('inf');self.sequence=-1
        self.counts=dict(frames=0,analyzed=0,rejected=0,preempted=0)

    def context(self,pid,sid):
        item=self.observation
        if (item and self.pid==pid and self.sid==sid and self.state=='capturing' and self.sharing.status()['mini_allowed']
            and self.frame and self.clock()-self.frame['at']<=3 and self.clock()-item['captured_at']<=30):return item['text']
        return None

    def status(self):
        now=self.clock();items=[]
        for risk in self.risks:
            if now-risk['at']>90:continue
            try:
                if any(self.store.citation(self.pid,cid)['superseded'] for cid in risk['citation_ids']):continue
                if any(not self.store.db.execute('SELECT 1 FROM transcript_segments WHERE id=? AND session_id=?',(sid,self.sid)).fetchone() for sid in risk['segment_ids']):continue
            except DomainError:continue
            if risk['screen_evidence'] and not self.context(self.pid,self.sid):continue
            items.append(risk)
        live=self.store.live()
        if not live or live['id']!=self.sid or live['state']!='active' or self.store.value('selected_project_id')!=self.pid:items=[]
        return {**self.native.diagnostics(),'state':self.state,'error':self.error,'selected':self.selected,'project_id':self.pid,'session_id':self.sid,
                'counts':dict(self.counts),'risks_enabled':self.risks_enabled,'risk_count':len(items),'risks':items,
                'observation_available':bool(self.context(self.pid,self.sid)),'preview_available':bool(self.frame and now-self.frame['at']<=3),
                'analysis_deferred':self.resources.manual_pending or self.resources.pressured()}

    async def select(self,pid,source_id):
        self.store.project(pid)
        if self.store.value('selected_project_id')!=pid:raise DomainError('Select this project first')
        if self.store.live() and self.store.live()['state']=='active':raise DomainError('Pause or stop before selecting a window')
        await self.stop()
        windows=await self.native.windows()
        selected=next((w for w in windows if w['id']==source_id),None) if source_id else None
        if source_id and not selected:raise DomainError('Window is no longer available',404)
        self.selected={**selected,'project_id':pid} if selected else None
        if not selected:self.paused_capture=False
        await self.notify()

    def preflight(self,pid,capture):
        if capture and (not self.selected or self.selected['project_id']!=pid):raise DomainError('Select a window in this project before starting',422)
        if capture and not self.native.diagnostics()['available']:raise DomainError(self.native.diagnostics()['reason'],503)
        if capture and not self.sharing.status()['mini_allowed']:raise DomainError('Acknowledge tab-only or no-sharing mode before capture',422)

    async def begin(self,pid,sid,capture=False,risks=False):
        await self.stop();self.pid,self.sid=pid,sid;self.risks_enabled=risks
        self.state='starting' if capture else 'off';self.error=None;self.changes=Changes();self.sequence=-1
        if capture:self.capture_task=asyncio.create_task(self._capture(self.selected['id']))
        if capture or risks:self.worker=asyncio.create_task(self._work())
        await self.notify()

    async def _capture(self,source_id):
        try:
            async for event in self.native.frames(source_id):
                if not self.sharing.status()['mini_allowed']:raise DomainError('Capture suspended for unverified sharing mode',409)
                if event['source_id']!=source_id or event['sequence']<=self.sequence:raise ValueError('Stale or wrong-source frame')
                png,jpeg,signature=await asyncio.to_thread(decode_frame,event)
                self.sequence=event['sequence'];now=self.clock();self.changes.update(signature,now)
                if self.observation:
                    if self.changes.analyzed is None or difference(signature,self.changes.analyzed)>self.changes.threshold:
                        self.observation=None;self.risks=[r for r in self.risks if not r['screen_evidence']]
                    else:self.observation['captured_at']=now
                self.frame=dict(png=png,jpeg=jpeg,signature=signature,at=now);self.counts['frames']+=1;self.state='capturing'
                if self.counts['frames']==1:await self.notify()
            raise DomainError('Selected-window stream ended',503)
        except asyncio.CancelledError:raise
        except Exception:
            self.state='error';self.error='Selected-window capture stopped; audio and document assistance remain available.'
            self.frame=self.observation=None;self.risks=[]
            if self.job:self.job.cancel()
            await self.notify()

    def preview(self):
        if not self.frame or self.clock()-self.frame['at']>3 or not self.sharing.status()['mini_allowed']:raise DomainError('No fresh selected-window preview is available',404)
        return self.frame['png']

    async def _work(self):
        while True:
            await asyncio.sleep(.5)
            live=self.store.live()
            if not live or live['id']!=self.sid or live['state']!='active':continue
            if self.resources.manual_pending or self.resources.pressured():continue
            if self.clock()-self.last_analysis<10:continue
            image=self.frame if self.frame and self.clock()-self.frame['at']<=3 and self.changes.ready(self.clock()) else None
            _,_,rows,digest=self.store.snapshot_window(self.pid,self.sid,time.time())
            text_changed=self.risks_enabled and rows and digest!=self.last_text_digest
            if not image and not text_changed:continue
            self.last_analysis=self.clock()
            if image:self.changes.attempted(self.clock())
            self.job=asyncio.create_task(self.analyze(image,rows if self.risks_enabled else [],digest))
            try:await self.job
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():raise
                self.counts['preempted']+=1
            finally:self.job=None

    async def analyze(self,image,rows,digest):
        try:
            async with asyncio.timeout(30), self.resources.lease('vision' if image else 'risk'):
                citations=[]
                if rows and self.risks_enabled:
                    result=await self.documents.search(self.pid,' '.join(r['text'] for r in rows[-3:])[:400],'lexical')
                    citations=[h['citation'] for h in result['hits'][:2]]
                messages,schema=analysis_prompt(rows,citations,bool(image))
                import json
                shown=json.loads(messages[1]['content'])
                rows=[r for r in rows if r['id'] in {s['id'] for s in shown['transcript']}]
                citations=[c for c in citations if c['citation_id'] in {s['id'] for s in shown['sources']}]
                async with self.documents.embed_lock:
                    identity=await self.generator.identity()
                    content,metrics=await self.generator.observe(messages,schema,image['jpeg'] if image else None)
                    if await self.generator.identity()!=identity:raise BriefingInvalid('Model changed during visual analysis')
                value=await asyncio.to_thread(validate_observation,content,rows,citations,bool(image))
                for cite in citations:
                    if self.store.citation(self.pid,cite['citation_id'])['superseded']:raise BriefingInvalid('Source changed during analysis')
                # Never publish observations from a superseded scene or after capture failed.
                if image and (not self.frame or self.state!='capturing' or self.changes.candidate_since>image['at']):return
                if image and value['observation']:
                    self.observation=dict(text=value['observation'],captured_at=image['at']);self.changes.accepted(image['signature'])
                self.risks=[{**r,'at':self.clock(),'citations':[c for c in citations if c['citation_id'] in r['citation_ids']],
                    'segments':[{'id':s['id'],'text':s['text']} for s in rows if s['id'] in r['segment_ids']]} for r in value['risks']] if self.risks_enabled else []
                self.last_text_digest=digest;self.counts['analyzed']+=1;self.error=None
                await self.notify()
        except ResourceDeferred as exc:
            self.error=str(exc);await self.notify()
        except asyncio.CancelledError:raise
        except (GenerationUnavailable,BriefingInvalid,DomainError):
            self.counts['rejected']+=1;self.error='Local visual/risk analysis unavailable or rejected; audio/document assistance continues.';await self.notify()
        except Exception:
            self.counts['rejected']+=1;self.error='Visual analysis failed within local resource limits.';await self.notify()

    async def stop(self,clear_selection=False):
        for task in (self.capture_task,self.worker,self.job):
            if task:task.cancel()
        await asyncio.gather(*[t for t in (self.capture_task,self.worker,self.job) if t],return_exceptions=True)
        await self.native.close();self.capture_task=self.worker=self.job=None
        self.frame=self.observation=None;self.risks=[];self.risks_enabled=False;self.state='idle';self.pid=self.sid=None
        self.last_analysis=-float('inf');self.last_text_digest=None
        if clear_selection:self.selected=None
