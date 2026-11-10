import asyncio
import io
import json
import time
import zipfile
from datetime import datetime,timezone
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pm_copilot.app import create_app
from pm_copilot.document_parser import parse_document,ParseError,MAX_UPLOAD
from pm_copilot.embeddings import EmbeddingUnavailable,MODEL,OllamaEmbeddings,normalize_vectors
from conftest import NoHardwareMeeting,NoModelEmbeddings
from test_app import project


def upload(client,pid,name,text,modified=None):
    params={'filename':name}
    if modified:params['modified_at']=modified
    data=text.encode() if isinstance(text,str) else text
    return client.post(f'/api/projects/{pid}/documents',params=params,content=data,headers={'Content-Type':'application/octet-stream'})


def finished(client,pid,did,expected=None):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        doc=next(x for x in client.get(f'/api/projects/{pid}/documents').json()['documents'] if x['id']==did)
        if doc['status'] in (expected,) if expected else doc['status'] in ('ready','lexical_ready','error'): return doc
        time.sleep(.03)
    raise AssertionError('Indexing did not finish: '+str(doc))


def search(client,pid,query,mode='lexical'):
    return client.post(f'/api/projects/{pid}/knowledge/search',json={'query':query,'mode':mode})


@pytest.mark.parametrize('name,text,expected',[
 ('plan.md','# Release\nrelease date: Friday\n','Release'),
 ('code.py','def launch():\n    return "Friday"\n','launch'),
 ('schema.graphql','type Release {\n date: String\n}\n','Release'),
 ('schema.proto','message Release {\n string date = 1;\n}\n','Release'),
 ('schema.sql','CREATE TABLE releases (id int);\n','releases'),
 ('plan.yaml','paths:\n  /release:\n    get:\n      summary: release date\n',''),
 ('data.json','{"updated_at":"2024-02-03T12:00:00Z","release":"Friday"}',''),
 ('data.xml','<release>Friday</release>',''),
 ('table.csv','feature,status\nrelease,Friday\n',''),
 ('notes.txt','Bulgarian: Здравей свят\n',''),
 ('ui.tsx','function Release() { return "Friday"; }\n','Release'),
 ('index.html','<script>throw new Error("do not execute")</script>',''),
])
def test_text_structure_and_literal_source_quotes(name,text,expected):
    result=parse_document(name,text.encode())
    assert result['chunks']
    for chunk in result['chunks']:
        loc=chunk['locator'];unit=result['units'][loc['unit']]['text']
        assert unit[loc['char_start']:loc['char_end']]==chunk['text']
    if expected: assert expected in result['chunks'][0]['locator']['heading']
    if name.endswith('.json'):assert result['internal_modified_at']=='2024-02-03T12:00:00+00:00'
    if name.endswith('.yaml'):assert any(x['locator'].get('endpoint')=='GET /release' for x in result['chunks'])


def office(kind):
    data=io.BytesIO()
    if kind=='docx':
        from docx import Document
        doc=Document();doc.core_properties.modified=datetime(2024,1,2,tzinfo=timezone.utc)
        doc.add_heading('Release',1);doc.add_paragraph('Friday launch evidence');table=doc.add_table(rows=1,cols=2)
        table.cell(0,0).text='Owner';table.cell(0,1).text='PM';doc.save(data)
    elif kind=='pptx':
        from pptx import Presentation
        deck=Presentation();deck.core_properties.modified=datetime(2024,1,2,tzinfo=timezone.utc)
        slide=deck.slides.add_slide(deck.slide_layouts[1]);slide.shapes.title.text='Release'
        slide.placeholders[1].text='Friday launch evidence';deck.save(data)
    elif kind=='xlsx':
        from openpyxl import Workbook
        book=Workbook();sheet=book.active;sheet.title='Release';sheet.append(['Owner','Friday']);sheet.append(['Formula','=1+1']);book.save(data)
    return data.getvalue()


@pytest.mark.parametrize('ext',['docx','pptx','xlsx'])
def test_actual_office_containers_have_precise_locators(ext):
    result=parse_document('release.'+ext,office(ext))
    assert any('Friday' in c['text'] for c in result['chunks'])
    assert result['internal_modified_at']
    if ext=='docx':assert any(c['locator'].get('paragraph')==2 for c in result['chunks'])
    if ext=='pptx':assert all(c['locator']['slide']==1 for c in result['chunks'])
    if ext=='xlsx':
        assert any(c['locator'].get('range')=='A1:B1' for c in result['chunks'])
        assert any('=1+1' in c['text'] for c in result['chunks'])


def pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(300,300)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 100 Td (Friday launch evidence) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream);writer.add_metadata({'/ModDate':"D:20240102120000+02'00'"})
    data=io.BytesIO();writer.write(data);return data.getvalue()


def test_actual_pdf_text_page_and_internal_revision():
    result=parse_document('plan.pdf',pdf())
    assert result['chunks'][0]['locator']['page']==1
    assert 'Friday launch evidence' in result['chunks'][0]['text']
    assert result['internal_modified_at']=='2024-01-02T10:00:00+00:00'


@pytest.mark.parametrize('name,data',[
 ('../secret.txt',b'hello'),('C:\\secret.py',b'hello'),('meeting.wav',b'raw'),
 ('a.xml',b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'),
 ('a.yaml',b'!!python/object/apply:os.system ["echo forbidden"]'),('a.json',b'{invalid'),
 ('a.txt',b'\x00binary'),('a.docx',b'not a document'),('a.pdf',b'not pdf'),
])
def test_invalid_imports_never_execute_or_become_searchable(name,data):
    with pytest.raises(ParseError):parse_document(name,data)


def test_macros_and_bomb_archives_are_rejected():
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('word/document.xml','<document/>');z.writestr('word/vbaProject.bin',b'never execute')
    with pytest.raises(ParseError,match='Macro'):parse_document('unsafe.docx',data.getvalue())
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('word/document.xml','x'*1000000)
    with pytest.raises(ParseError,match='compression'):parse_document('bomb.docx',data.getvalue())


def test_real_api_ingestion_search_citation_and_revision_retention(client):
    p=project(client);raw='# Plan\nlaunch date: Friday\nupdated_at: 2024-02-03\n'
    response=upload(client,p,'plan.md',raw,'2025-05-05T12:00:00Z');assert response.status_code==202
    first=response.json();doc=finished(client,p,first['document_id']);assert doc['status']=='lexical_ready'
    assert doc['revision_basis']=='internal' and doc['revision_time'].startswith('2024-02-03')
    result=search(client,p,'launch date').json();assert result['hits']
    cite=result['hits'][0]['citation'];assert cite['quote'] in raw and cite['locator']['line_start']==1
    assert client.get(f'/api/projects/{p}/citations/{cite["citation_id"]}').json()==cite
    same=upload(client,p,'plan.md',raw).json();assert same['unchanged'] and same['revision_id']==first['revision_id']
    second=upload(client,p,'plan.md','# Plan\nlaunch date: Monday\n').json();assert second['document_id']==first['document_id'] and second['revision_id']!=first['revision_id']
    assert finished(client,p,first['document_id'])['version']==2
    old=client.get(f'/api/projects/{p}/citations/{cite["citation_id"]}').json();assert old['superseded'] and old['quote']==cite['quote']
    assert not search(client,p,'Friday').json()['hits']
    assert search(client,p,'Monday').json()['hits']


def test_project_search_and_citation_scope_are_strict(client):
    a=project(client,'Alpha');b=project(client,'Beta')
    da=upload(client,a,'plan.txt','Only Alpha has ALPHA_SECRET\n').json();finished(client,a,da['document_id'])
    db=upload(client,b,'plan.txt','Only Beta has BETA_SECRET\n').json();finished(client,b,db['document_id'])
    assert search(client,a,'BETA_SECRET').json()['hits']==[]
    cid=search(client,b,'BETA_SECRET').json()['hits'][0]['citation']['citation_id']
    assert client.get(f'/api/projects/{a}/citations/{cid}').status_code==404
    check=client.post(f'/api/projects/{a}/citations/verify',json={'citation_ids':[cid,'invented']}).json()
    assert check=={'valid':[],'invalid':[cid,'invented']}
    assert client.get(f'/api/projects/{a}/documents/{db["document_id"]}/chunks').status_code==404
    assert client.delete(f'/api/projects/{a}/documents/{db["document_id"]}').status_code==404
    assert client.delete(f'/api/projects/{a}').status_code==200
    assert search(client,b,'BETA_SECRET').json()['hits']


def test_conflicting_facts_prefer_internal_revision_date(client):
    p=project(client)
    new=upload(client,p,'current.md','updated_at: 2026-01-01\nrelease date: Friday\n','2020-01-01').json();finished(client,p,new['document_id'])
    old=upload(client,p,'old.md','updated_at: 2024-01-01\nrelease date: Monday\n','2030-01-01').json();finished(client,p,old['document_id'])
    conflicts=search(client,p,'release date').json()['conflicts']
    match=next(c for c in conflicts if c['subject']=='release date')
    preferred=client.get(f'/api/projects/{p}/citations/{match["preferred_citation_id"]}').json()
    assert preferred['filename']=='current.md' and preferred['revision_basis']=='internal'
    for evidence in match['evidence']:assert client.get(f'/api/projects/{p}/citations/{evidence["citation_id"]}').status_code==200


def test_citation_corruption_and_document_delete_invalidate_references(client):
    p=project(client);doc=upload(client,p,'source.txt','Check exact evidence\n').json();finished(client,p,doc['document_id'])
    cid=search(client,p,'evidence').json()['hits'][0]['citation']['citation_id']
    store=client.app.state.store
    with store.db:store.db.execute('UPDATE document_chunks SET text=? WHERE id=?',('tampered',cid))
    assert client.get(f'/api/projects/{p}/citations/{cid}').status_code==409
    assert client.post(f'/api/projects/{p}/citations/verify',json={'citation_ids':[cid]}).json()['invalid']==[cid]
    assert client.delete(f'/api/projects/{p}/documents/{doc["document_id"]}').status_code==200
    assert client.get(f'/api/projects/{p}/citations/{cid}').status_code==404


def test_failed_import_progress_and_upload_validation(client):
    p=project(client)
    assert upload(client,p,'../../escape.txt','never written').status_code==422
    assert upload(client,p,'a.txt',b'a'*(MAX_UPLOAD+1)).status_code==413
    result=upload(client,p,'bad.pdf',b'not pdf').json();doc=finished(client,p,result['document_id'])
    assert doc['status']=='error' and doc['chunk_count']==0 and doc['error']
    assert search(client,p,'not pdf').json()['hits']==[]


def test_indexing_defers_while_session_is_active(client):
    p=project(client);client.post(f'/api/projects/{p}/select')
    s=client.post('/api/sessions',json={'consent':True,'project_id':p}).json()['session']['id']
    doc=upload(client,p,'queued.txt','Deferred indexing content').json()
    time.sleep(.1)
    assert client.get(f'/api/projects/{p}/documents').json()['documents'][0]['status']=='queued'
    client.post(f'/api/sessions/{s}/stop')
    assert finished(client,p,doc['document_id'])['chunk_count']>0


class FixtureEmbeddings:
    model=MODEL
    def __init__(self):self.digest='a'*64;self.inputs=[]
    async def identity(self,refresh=False):return self.digest
    async def embed(self,texts,query=False):
        self.inputs.extend((t,query) for t in texts)
        return normalize_vectors([[1,0,0] if any(w in t.casefold() for w in ['launch','timeline']) else [0,1,0] for t in texts],len(texts))


def test_fixture_semantic_ranking_persisted_cache_and_model_digest(tmp_path):
    embed=FixtureEmbeddings();db=tmp_path/'docs.sqlite3'
    app=create_app(db,'test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=lambda:embed)
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:
        p=project(c)
        first=upload(c,p,'launch.md','# Stable\nlaunch plan\n# Version\nversion: one\n').json();assert finished(c,p,first['document_id'])['status']=='ready'
        assert search(c,p,'timeline','lexical').json()['hits']==[]
        result=search(c,p,'timeline','semantic');assert result.status_code==200 and result.json()['hits'][0]['citation']['filename']=='launch.md'
        before=len([x for x in embed.inputs if not x[1]])
        upload(c,p,'launch.md','# Stable\nlaunch plan\n# Version\nversion: two\n');finished(c,p,first['document_id'])
        after=len([x for x in embed.inputs if not x[1]])
        assert after-before==1  # unchanged section reused the persisted vector
        embed.digest='b'*64
        assert search(c,p,'timeline','semantic').status_code==503
        c.post(f'/api/projects/{p}/documents/{first["document_id"]}/reindex')
        finished(c,p,first['document_id'],expected='ready')
        assert search(c,p,'timeline','semantic').status_code==200
    calls=len(embed.inputs)
    with TestClient(create_app(db,'test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=lambda:embed),base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:
        assert search(c,p,'timeline','semantic').json()['hits']
    assert len(embed.inputs)==calls+1 # query only; no re-embedding on restart


def test_unavailable_embeddings_are_explicit(client):
    p=project(client);doc=upload(client,p,'lexical.txt','launch date: Friday').json();finished(client,p,doc['document_id'])
    result=search(client,p,'launch','hybrid').json();assert result['mode']=='lexical' and result['warning'] and result['hits']
    assert search(client,p,'launch','semantic').status_code==503


@pytest.mark.parametrize('vectors',[[[0,0]],[[float('nan'),1]],[[float('inf'),1]],[[1,2],[3]],[[1e38,1e38]]])
def test_invalid_embedding_vectors_are_not_persisted(vectors):
    with np.errstate(over='ignore'):
        with pytest.raises(EmbeddingUnavailable):normalize_vectors(vectors,1)


def test_ollama_client_requests_only_loopback_cpu_and_unloads(monkeypatch):
    import httpx
    calls=[];original=httpx.AsyncClient
    def handle(request):
        calls.append(request)
        assert request.url.host=='127.0.0.1' and request.url.port==11434
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':MODEL,'digest':'a'*64}]})
        body=json.loads(request.content);assert body['keep_alive']==0 and body['options']['num_gpu']==0 and body['truncate'] is False
        assert body['input'][0].startswith('Instruct:')
        return httpx.Response(200,json={'embeddings':[[3,4]]})
    def factory(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handle),**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',factory)
    async def check():
        model=OllamaEmbeddings();assert await model.identity()=='a'*64
        vector=(await model.embed(['timeline'],query=True))[0]
        assert np.allclose(vector,[.6,.8])
    asyncio.run(check());assert len(calls)==2


def test_citation_locator_tampering_is_rejected(client):
    p=project(client);doc=upload(client,p,'source.txt','Line one\nLine two\n').json();finished(client,p,doc['document_id'])
    cid=search(client,p,'Line').json()['hits'][0]['citation']['citation_id']
    store=client.app.state.store
    row=store.db.execute('SELECT locator FROM document_chunks WHERE id=?',(cid,)).fetchone()
    locator=json.loads(row[0]);locator['line_start']=999
    with store.db:store.db.execute('UPDATE document_chunks SET locator=? WHERE id=?',(json.dumps(locator),cid))
    assert client.get(f'/api/projects/{p}/citations/{cid}').status_code==409


def test_project_file_limit_allows_updating_an_existing_file(client):
    store=client.app.state.store;p=project(client)
    for i in range(50):store.upload_document(p,f'doc-{i}.txt',f'file {i}'.encode())
    from pm_copilot.store import DomainError
    with pytest.raises(DomainError):store.upload_document(p,'overflow.txt',b'too many')
    result=store.upload_document(p,'doc-0.txt',b'updated content')
    assert not result['unchanged'] and len(store.list_documents(p))==50


def test_imported_python_code_is_never_executed(tmp_path):
    sentinel=tmp_path/'never-created'
    body=f'from pathlib import Path\nPath({str(sentinel)!r}).write_text("forbidden")\n'
    parsed=parse_document('untrusted.py',body.encode())
    assert parsed['chunks'] and not sentinel.exists()


def test_semantic_fixture_results_and_vectors_do_not_cross_projects(tmp_path):
    embed=FixtureEmbeddings()
    app=create_app(tmp_path/'scope.sqlite3','test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=lambda:embed)
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:
        a=project(c,'Alpha');b=project(c,'Beta')
        da=upload(c,a,'a.txt','launch plan').json();finished(c,a,da['document_id'],expected='ready')
        db=upload(c,b,'b.txt','budget figures').json();finished(c,b,db['document_id'],expected='ready')
        assert search(c,a,'timeline','semantic').json()['hits']
        assert search(c,b,'timeline','semantic').json()['hits']==[]


def test_queued_originals_resume_after_restart(tmp_path):
    path=tmp_path/'recover.sqlite3'
    def connection():return TestClient(create_app(path,'test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=NoModelEmbeddings),base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'})
    with connection() as c:
        p=project(c);c.post(f'/api/projects/{p}/select');c.post('/api/sessions',json={'consent':True,'project_id':p})
        doc=upload(c,p,'queued.txt','Persistent queued evidence').json()
        assert c.get(f'/api/projects/{p}/documents').json()['documents'][0]['status']=='queued'
    with connection() as c:
        assert finished(c,p,doc['document_id'])['status']=='lexical_ready'
        assert search(c,p,'queued evidence').json()['hits']
