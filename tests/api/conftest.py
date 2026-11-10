import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'services/api'))
from pm_copilot.app import create_app
from pm_copilot.meeting import Meeting
from pm_copilot.embeddings import EmbeddingUnavailable, MODEL

class NoModelEmbeddings:
    model=MODEL
    async def identity(self,refresh=False): raise EmbeddingUnavailable("No embedding model in portable fixtures")


class NoHardwareMeeting(Meeting):
    def diagnostics(self):
        return {'available':False,'reason':'Capture is disabled in portable tests','process_loopback':False,'diarization_model_present':False}
    async def enumerate_devices(self):
        return {'devices':[],'reason':'Capture is disabled in portable tests','process_loopback':False}


@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path/'test.sqlite3','test-secret','http://127.0.0.1:8750',meeting_factory=NoHardwareMeeting,embedding_factory=NoModelEmbeddings)
    with TestClient(app,base_url='http://127.0.0.1:8750',headers={'Authorization':'Bearer test-secret'}) as c:
        yield c
