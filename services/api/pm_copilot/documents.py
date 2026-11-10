import asyncio
import base64
import importlib.metadata
import json
import sys
from pathlib import Path
from .document_parser import MAX_UPLOAD, validate_name
from .embeddings import OllamaEmbeddings, EmbeddingUnavailable, cosine_candidates
from .store import DomainError
from .runtime import command, cwd


class Documents:
    def __init__(self, store, change, embedder=None):
        self.store,self.change=store,change
        self.embedder=embedder or OllamaEmbeddings()
        self.wake=asyncio.Event();self.task=None;self.process=None
        self.embed_lock=asyncio.Lock();self.search_lock=asyncio.Semaphore(2)
        self.stopped=False;self.manual_active=False

    def dependencies(self):
        packages={}
        for package in ['pypdf','python-docx','python-pptx','openpyxl','defusedxml','numpy','PyYAML','httpx']:
            try: packages[package]=importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError: packages[package]=None
        return {'fts5':self.store.fts5_supported,'packages':packages,'model':self.embedder.model,
                'missing_packages':[p for p,v in packages.items() if v is None]}

    async def status(self):
        result=self.dependencies()
        try: digest=await self.embedder.identity()
        except EmbeddingUnavailable as exc: return {**result,'embeddings_available':False,'model_digest':None,'reason':str(exc)}
        return {**result,'embeddings_available':True,'model_digest':digest,'reason':None}

    def start(self):
        self.task=asyncio.create_task(self._run());self.wake.set()

    async def close(self):
        self.stopped=True
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if self.process and self.process.returncode is None:
            self.process.kill();await self.process.wait()

    async def upload(self, project_id, name, data, modified=None):
        validate_name(name)
        if not data or len(data)>MAX_UPLOAD: raise DomainError('Document must be between 1 byte and 20 MiB',413)
        if self.dependencies()['missing_packages']:
            raise DomainError('Install requirements-documents.lock before importing documents',503)
        result={}
        def create(): result.update(self.store.upload_document(project_id,name,data,modified))
        await self.change(create)
        self.wake.set()
        return result

    async def reindex(self, project_id, document_id):
        await self.change(self.store.reindex_document,project_id,document_id);self.wake.set()

    async def _parse(self, job):
        self.process=await asyncio.create_subprocess_exec(*command('document'),cwd=cwd(),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x00004000 if sys.platform=='win32' else 0)
        message={'name':job['name'],'content':base64.b64encode(job['original']).decode()}
        try:
            async def write():
                try:
                    self.process.stdin.write((json.dumps(message)+'\n').encode())
                    await self.process.stdin.drain()
                    self.process.stdin.close()
                except (BrokenPipeError,ConnectionResetError): pass
            async def read():
                output=bytearray()
                while True:
                    part=await self.process.stdout.read(65536)
                    if not part: return bytes(output)
                    if len(output)+len(part)>32*1024*1024: raise DomainError('Parser output exceeded limits',422)
                    output.extend(part)
            tasks=[asyncio.create_task(write()),asyncio.create_task(read())]
            try:
                _,output=await asyncio.wait_for(asyncio.gather(*tasks),45)
                await self.process.wait()
            finally:
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
            result=json.loads(output)
            if result.get('type')!='parsed': raise DomainError(result.get('detail','Parser failed'),422)
            return result['result']
        except (asyncio.TimeoutError,ValueError): raise DomainError('Parser failed or exceeded its time/memory limit',422)
        finally:
            if self.process.returncode is None: self.process.kill();await self.process.wait()
            self.process=None

    def active_meeting(self):
        row=self.store.live()
        return self.manual_active or bool(row and row['state']=='active')

    async def _run(self):
        while not self.stopped:
            try:
                await asyncio.wait_for(self.wake.wait(),2)
            except asyncio.TimeoutError: pass
            self.wake.clear()
            while not self.stopped and not self.active_meeting():
                job=self.store.next_document_job()
                if not job: break
                try: await self._job(job)
                except asyncio.CancelledError: raise
                except Exception:
                    await self.change(self.store.document_state,job['document_id'],job['revision_id'],'error','error',0,'Indexing failed within local resource limits')
                if self.active_meeting(): break

    async def _job(self, job):
        pid,did,rid=job['project_id'],job['document_id'],job['revision_id']
        if job['units'] is None:
            await self.change(self.store.document_state,did,rid,'parsing','extracting source text',.1)
            try: parsed=await self._parse(job)
            except DomainError as exc:
                await self.change(self.store.document_state,did,rid,'error','parse failed',0,exc.message);return
            await self.change(self.store.commit_parsed,pid,did,rid,parsed)
        if not self.store.document_job_current(did,rid): return
        if self.active_meeting():
            await self.change(self.store.document_state,did,rid,'queued','deferred until session stops',.5);return
        try:
            digest=await self.embedder.identity(refresh=True)
            chunks=self.store.revision_chunks(pid,rid)
            await self.change(self.store.document_state,did,rid,'indexing_embeddings','local CPU embeddings',.5)
            for offset in range(0,len(chunks),8):
                if not self.store.document_job_current(did,rid): return
                if self.active_meeting():
                    await self.change(self.store.document_state,did,rid,'queued','deferred until session stops',.5);return
                batch=chunks[offset:offset+8]
                cached=self.store.embedding_cache(pid,self.embedder.model,digest,[c['text_hash'] for c in batch])
                missing={c['text_hash']:c for c in batch if c['text_hash'] not in cached}
                if missing:
                    async with self.embed_lock:
                        vectors=await self.embedder.embed([c['text'] for c in missing.values()])
                        if await self.embedder.identity(refresh=True)!=digest: raise EmbeddingUnavailable('Embedding model changed during indexing; retry reindex')
                    saved=[(key,len(vector),vector.astype('<f4').tobytes()) for key,vector in zip(missing,vectors)]
                    if self.store.document_job_current(did,rid): await self.change(self.store.save_embeddings,pid,self.embedder.model,digest,saved)
                await self.change(self.store.document_state,did,rid,'indexing_embeddings','local CPU embeddings',.5+.5*min(1,(offset+8)/max(1,len(chunks))))
            await self.change(self.store.indexed_document,did,rid,digest)
        except EmbeddingUnavailable as exc:
            await self.change(self.store.document_state,did,rid,'lexical_ready','lexical search available',.5,str(exc))

    async def search(self, project_id, query, mode='hybrid'):
        async with self.search_lock:
            self.store.project(project_id)
            lexical=self.store.lexical_candidates(project_id,query)
            semantic=[];warning=None;digest=None
            if mode!='lexical':
                try:
                    async with self.embed_lock:
                        digest=await self.embedder.identity()
                        vector=(await self.embedder.embed([query],query=True))[0]
                        if await self.embedder.identity(refresh=True)!=digest: raise EmbeddingUnavailable('Embedding model changed during query; retry search')
                    rows=self.store.semantic_rows(project_id,self.embedder.model,digest)
                    if not rows: raise EmbeddingUnavailable('No embeddings for the current model digest; reindex documents')
                    semantic=await asyncio.to_thread(cosine_candidates,rows,vector)
                except EmbeddingUnavailable as exc:
                    if mode=='semantic': raise DomainError(str(exc),503)
                    warning=str(exc)
            candidates={};scores={}
            if mode!='semantic':
                for rank,row in enumerate(lexical,1): candidates[row['id']]=row;scores[row['id']]=1/(60+rank)
            for rank,(row,similarity) in enumerate(semantic,1):
                candidates[row['id']]=row;scores[row['id']]=scores.get(row['id'],0)+1/(60+rank)
            ordered=sorted(candidates.values(),key=lambda r:(round(scores[r['id']],4),r['revision_time']),reverse=True)[:10]
            hits=[]
            for row in ordered:
                # Resolve against the actual stored source before returning ANY citation.
                cite=self.store.citation(project_id,row['id'])
                hits.append({'citation':cite,'score':scores[row['id']]})
            return {'mode':mode if mode=='lexical' or warning is None else 'lexical',
                    'warning':warning,'model_digest':digest,'hits':hits,
                    'conflicts':self.store.knowledge_conflicts(project_id,query,[x['id'] for x in ordered])}
