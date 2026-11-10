"""Project-scoped document endpoints registered inside the existing authenticated API."""
from typing import Literal
from fastapi import Request
from pydantic import BaseModel,ConfigDict,Field
from .document_parser import MAX_UPLOAD, ParseError, timestamp, validate_name
from .store import DomainError


class DocumentSummary(BaseModel):
    id: str
    name: str
    current_revision: str
    status: str
    phase: str
    progress: float
    error: str | None
    warnings: list[str]
    model_digest: str | None
    version: int
    content_hash: str
    revision_time: str
    revision_basis: str
    imported_at: str
    chunk_count: int


class DocumentList(BaseModel):
    documents: list[DocumentSummary]


class DocumentUpload(BaseModel):
    document_id: str
    revision_id: str
    unchanged: bool


class KnowledgeStatus(BaseModel):
    fts5: bool
    packages: dict[str,str | None]
    model: str
    missing_packages: list[str]
    embeddings_available: bool
    model_digest: str | None
    reason: str | None


class Citation(BaseModel):
    citation_id: str
    document_id: str
    filename: str
    revision_id: str
    version: int
    content_hash: str
    revision_time: str
    revision_basis: str
    locator: dict[str,str | int]
    quote: str
    preview: str
    preview_start: int
    superseded: bool


class SearchRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query: str=Field(min_length=1,max_length=500)
    mode: Literal['lexical','hybrid','semantic']='hybrid'


class SearchHit(BaseModel):
    citation: Citation
    score: float


class ConflictEvidence(BaseModel):
    citation_id: str
    document_id: str
    value: str
    revision_time: str


class Conflict(BaseModel):
    subject: str
    scope: str
    preferred_citation_id: str
    evidence: list[ConflictEvidence]
    warning: str


class SearchResponse(BaseModel):
    mode: Literal['lexical','hybrid','semantic']
    warning: str | None
    model_digest: str | None
    hits: list[SearchHit]
    conflicts: list[Conflict]


class VerifyRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    citation_ids: list[str]=Field(max_length=50)


class VerifyResponse(BaseModel):
    valid: list[Citation]
    invalid: list[str]


def register_document_routes(app,store,documents,change):
    import asyncio
    uploads=asyncio.Semaphore(2)

    @app.get('/api/knowledge/status',response_model=KnowledgeStatus)
    async def status(): return await documents.status()

    @app.get('/api/projects/{project_id}/documents',response_model=DocumentList)
    async def listing(project_id: str): return {'documents':store.list_documents(project_id)}

    @app.post('/api/projects/{project_id}/documents',response_model=DocumentUpload,status_code=202,openapi_extra={'requestBody':{'required':True,'content':{'application/octet-stream':{'schema':{'type':'string','format':'binary'}}}}})
    async def upload(project_id: str, filename: str, request: Request, modified_at: str | None=None):
        store.project(project_id)
        try: validate_name(filename)
        except ParseError as exc: raise DomainError(str(exc),422)
        if modified_at is not None and timestamp(modified_at) is None: raise DomainError('Invalid original file modification timestamp',422)
        if request.headers.get('content-type','').split(';')[0]!='application/octet-stream':
            raise DomainError('Use an application/octet-stream body',415)
        async with uploads:
            data=bytearray()
            async for part in request.stream():
                if len(data)+len(part)>MAX_UPLOAD: raise DomainError('Document exceeds 20 MiB',413)
                data.extend(part)
            return await documents.upload(project_id,filename,bytes(data),modified_at)

    @app.delete('/api/projects/{project_id}/documents/{document_id}')
    async def delete(project_id: str,document_id: str):
        await change(store.delete_document,project_id,document_id)
        return {'deleted':True}

    @app.post('/api/projects/{project_id}/documents/{document_id}/reindex')
    async def reindex(project_id: str,document_id: str):
        await documents.reindex(project_id,document_id)
        return {'queued':True}

    @app.get('/api/projects/{project_id}/documents/{document_id}/chunks',response_model=list[Citation])
    async def chunks(project_id: str,document_id: str,after: int=-1):
        document=store.document(project_id,document_id)
        rows=store.db.execute('SELECT id FROM document_chunks WHERE project_id=? AND document_id=? AND revision_id=? AND ordinal>? ORDER BY ordinal LIMIT 100',
            (project_id,document_id,document['current_revision'],after)).fetchall()
        return [store.citation(project_id,r['id']) for r in rows]

    @app.post('/api/projects/{project_id}/knowledge/search',response_model=SearchResponse)
    async def search(project_id: str,body: SearchRequest): return await documents.search(project_id,body.query,body.mode)

    @app.get('/api/projects/{project_id}/citations/{citation_id}',response_model=Citation)
    async def citation(project_id: str,citation_id: str): return store.citation(project_id,citation_id)

    @app.post('/api/projects/{project_id}/citations/verify',response_model=VerifyResponse)
    async def verify(project_id: str,body: VerifyRequest):
        store.project(project_id);valid=[];invalid=[]
        for cid in dict.fromkeys(body.citation_ids):
            try: valid.append(store.citation(project_id,cid))
            except DomainError: invalid.append(cid)
        return {'valid':valid,'invalid':invalid}
