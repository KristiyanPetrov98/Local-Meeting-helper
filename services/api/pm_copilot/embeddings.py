"""Ollama embeddings through a fixed loopback address. No hosted fallback."""
from .ollama_http import ollama_client
import math
import re
import time

MODEL='qwen3-embedding:0.6b'


class EmbeddingUnavailable(RuntimeError): pass


def normalize_vectors(values, count):
    try: import numpy as np
    except ImportError as exc: raise EmbeddingUnavailable('Install the NumPy document-search dependency') from exc
    try: array=np.asarray(values,dtype=np.float32)
    except (ValueError,TypeError) as exc: raise EmbeddingUnavailable('Invalid embedding response') from exc
    if array.ndim!=2 or array.shape[0]!=count or not 1<=array.shape[1]<=4096 or not np.isfinite(array).all():
        raise EmbeddingUnavailable('Invalid embedding dimensions or values')
    norms=np.linalg.norm(array,axis=1,keepdims=True)
    if not np.isfinite(norms).all() or (norms<1e-12).any(): raise EmbeddingUnavailable('Zero-length embedding received')
    return array/norms


class OllamaEmbeddings:
    model=MODEL
    def __init__(self):
        self.cached=None;self.checked=0.

    async def _call(self, path, data=None):
        try:
            import httpx
            async with ollama_client(timeout=60) as client:
                response=await client.request('GET' if data is None else 'POST','http://127.0.0.1:11434/api/'+path,json=data)
                if response.status_code!=200: raise EmbeddingUnavailable('Local Ollama request failed; check its model and runtime')
                return response.json()
        except EmbeddingUnavailable: raise
        except Exception as exc: raise EmbeddingUnavailable('Local Ollama is unavailable; install it and pull '+self.model) from exc

    async def identity(self, refresh=False):
        if not refresh and self.cached and time.monotonic()-self.checked<10: return self.cached
        try:
            payload=await self._call('tags')
            found=next(m for m in payload['models'] if m.get('name')==self.model or m.get('model')==self.model)
            digest=found['digest']
            if not isinstance(digest,str) or not re.fullmatch(r'(?:sha256:)?[a-fA-F0-9]{64}',digest):
                raise EmbeddingUnavailable('Ollama returned an invalid model identity')
        except (KeyError,StopIteration,TypeError) as exc:
            raise EmbeddingUnavailable('Install the exact Ollama model '+self.model) from exc
        self.cached=digest;self.checked=time.monotonic()
        return digest

    async def embed(self, texts, query=False):
        inputs=['Instruct: Given a project question, retrieve relevant passages that answer the question.\nQuery: '+t if query else t for t in texts]
        payload=await self._call('embed',{'model':self.model,'input':inputs,'truncate':False,
                                        'options':{'num_gpu':0,'num_ctx':2048},'keep_alive':0})
        return normalize_vectors(payload.get('embeddings'),len(texts))


def cosine_candidates(rows, query):
    """Bounded NumPy batches; no database use in this CPU worker."""
    import numpy as np
    ranked=[]
    for offset in range(0,len(rows),512):
        batch=rows[offset:offset+512]
        if any(row['dimensions']!=len(query) or len(row['vector'])!=len(query)*4 for row in batch):
            raise EmbeddingUnavailable('Stored vector dimensions differ; reindex the documents')
        matrix=np.stack([np.frombuffer(row['vector'],dtype='<f4') for row in batch])
        scores=matrix@query
        for row,score in zip(batch,scores):
            if math.isfinite(float(score)) and score>.15:
                ranked.append(({k:v for k,v in row.items() if k not in ('vector','dimensions')},float(score)))
    return sorted(ranked,key=lambda x:x[1],reverse=True)[:60]
