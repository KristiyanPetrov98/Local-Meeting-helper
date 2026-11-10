"""Regression checks for responsive local inference and stalled retrieval."""
import asyncio
import ssl
import time
from uuid import uuid4
import httpx
import pytest
from pm_copilot.ollama_http import ollama_client
from pm_copilot.documents import Documents
from pm_copilot.store import Store,DomainError
from pm_copilot.document_parser import parse_document
from test_documents import FixtureEmbeddings
from test_assistance import fixture_client,scope,trigger,finished


def test_local_http_client_does_not_load_tls_certificates(monkeypatch):
    def unexpected(*args,**kwargs):raise AssertionError('CA loading blocks the event loop')
    monkeypatch.setattr(ssl,'create_default_context',unexpected)
    async def check():
        # Construct the real transport (MockTransport would skip TLS setup).
        async with ollama_client(timeout=1) as client:
            assert not client.follow_redirects
    asyncio.run(check())


@pytest.mark.parametrize('url',['https://127.0.0.1:11434/api/tags','http://example.com/api/tags','http://127.0.0.1:11435/api/tags'])
def test_http_only_transport_rejects_other_destinations(url):
    async def check():
        async with ollama_client(timeout=1) as client:
            with pytest.raises(ValueError,match='only permits'):await client.get(url)
    asyncio.run(check())


@pytest.mark.parametrize('phase',['lock','identity','embedding'])
@pytest.mark.parametrize('mode',['hybrid','semantic'])
def test_retrieval_budget_bounds_model_and_lock_waits(tmp_path,monkeypatch,phase,mode):
    monkeypatch.setattr('pm_copilot.documents.QUERY_EMBEDDING_SECONDS',.03)
    async def check():
        store=Store(tmp_path/'search.sqlite3');pid=store.create('Search')['projects'][0]['id']
        doc=store.upload_document(pid,'release.txt',b'The release is Friday.')
        store.commit_parsed(pid,doc['document_id'],doc['revision_id'],parse_document('release.txt',b'The release is Friday.'))
        import numpy as np
        chunk=store.revision_chunks(pid,doc['revision_id'])[0]
        store.save_embeddings(pid,FixtureEmbeddings.model,'a'*64,[(chunk['text_hash'],3,np.array([1,0,0],dtype='<f4').tobytes())])
        class Slow(FixtureEmbeddings):
            async def identity(self,refresh=False):
                if phase=='identity':await asyncio.sleep(60)
                return self.digest
            async def embed(self,*args,**kwargs):await asyncio.sleep(60)
        async def change(*args):pass
        documents=Documents(store,change,Slow())
        if phase=='lock':await documents.embed_lock.acquire()
        try:
            if mode=='semantic':
                with pytest.raises(DomainError) as exc:await asyncio.wait_for(documents.search(pid,'release',mode),1)
                assert exc.value.status==503
            else:
                result=await asyncio.wait_for(documents.search(pid,'release',mode),1)
                assert result['mode']=='lexical' and 'budget' in result['warning']
                assert result['hits'][0]['citation']['quote']=='The release is Friday.'
        finally:
            if documents.embed_lock.locked():documents.embed_lock.release()
            store.close()
    asyncio.run(check())


def test_empty_index_does_not_load_query_embedding_model(tmp_path):
    async def check():
        store=Store(tmp_path/'empty.sqlite3');pid=store.create('Empty')['projects'][0]['id']
        class NeverEmbed(FixtureEmbeddings):
            async def embed(self,*args,**kwargs):raise AssertionError('No indexed evidence to search')
        documents=Documents(store,None,NeverEmbed())
        result=await documents.search(pid,'How many letters are there?')
        assert result['hits']==[] and result['mode']=='lexical' and result['warning']
        store.close()
    asyncio.run(check())


@pytest.mark.parametrize('action',['cancel','deadline','fallback'])
def test_stalled_retrieval_keeps_api_and_request_lifecycle_responsive(fixture_client,monkeypatch,action):
    c,gen=fixture_client;pid,sid,base,_=scope(c,text="When is the release?",evidence=True)
    docs=c.app.state.documents
    if action=='deadline':c.app.state.assistance.deadline=.05
    if action=='fallback':monkeypatch.setattr('pm_copilot.documents.QUERY_EMBEDDING_SECONDS',.05)
    c.portal.call(docs.embed_lock.acquire)
    rid=str(uuid4())
    try:
        assert trigger(c,base,rid).status_code==202
        assert c.get('/api/state').status_code==200
        if action=='cancel':
            started=time.monotonic();response=c.post(base+'/'+rid+'/cancel')
            assert response.status_code==200 and response.json()['status']=='cancelled'
            assert time.monotonic()-started<2
        elif action=='deadline':
            result=finished(c,base,rid,'error');assert 'deadline' in result['error']
        else:
            # Release after retrieval's own budget; generation shares this lock.
            time.sleep(.1);c.portal.call(docs.embed_lock.release)
            result=finished(c,base,rid,'completed')
            assert result['citations'] and any('budget' in w for w in result['warnings'])
        assert not c.get('/api/state').json()['assistance']['busy']
    finally:
        if docs.embed_lock.locked():c.portal.call(docs.embed_lock.release)
