"""M7 regression checks against the actual authenticated API and SQLite store."""
import json
import sqlite3
import pytest
from starlette.websockets import WebSocketDisconnect
from pm_copilot.security import JSON_BODY_LIMIT, token_matches
from pm_copilot.document_parser import parse_document
from pm_copilot.store import DomainError, Store
from test_app import project
from test_documents import upload, finished


@pytest.mark.parametrize('value', [None, 123, [], {}, 'Български', 'bad', ''])
def test_invalid_tokens_fail_without_type_errors(value):
    assert not token_matches(value, 'secret')


@pytest.mark.parametrize('payload', [[], {}, {'token': 123}, {'token': ['test-secret']},
                                    {'token': 'Български'}, {'token': 'x' * 600}])
def test_websocket_rejects_malformed_credentials(client, payload):
    with client.websocket_connect('ws://127.0.0.1:8750/api/events', headers={'Origin': 'http://127.0.0.1:8750'}) as ws:
        ws.send_json(payload)
        with pytest.raises(WebSocketDisconnect) as exc: ws.receive_json()
        assert exc.value.code == 1008


def test_websocket_binary_and_client_commands_close_cleanly(client):
    for authenticated in (False, True):
        with client.websocket_connect('ws://127.0.0.1:8750/api/events', headers={'Origin': 'http://127.0.0.1:8750'}) as ws:
            if authenticated:
                ws.send_json({'token': 'test-secret'}); ws.receive_json()
            ws.send_bytes(b'not a supported command')
            with pytest.raises(WebSocketDisconnect) as exc: ws.receive_json()
            assert exc.value.code == 1008
    assert client.get('/api/state').status_code == 200


def test_request_size_limit_covers_content_length_streams_and_content_type(client):
    for content_type in ('application/json', 'application/octet-stream'):
        response = client.post('/api/projects', content=b' ' * (JSON_BODY_LIMIT + 1), headers={'Content-Type': content_type})
        assert response.status_code == 413
    chunks = (b' ' * 16384 for _ in range(6))
    response = client.post('/api/projects', content=chunks, headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
    assert response.headers['cache-control'] == 'no-store'
    assert client.get('/api/state').json()['projects'] == []
    # Document uploads retain the separate 20 MiB ceiling.
    pid = project(client)
    response = upload(client, pid, 'bounded.txt', ('Evidence.\n' * 10000))
    assert response.status_code == 202, response.text
    assert finished(client, pid, response.json()['document_id'])['status'] == 'lexical_ready'


def test_validation_does_not_echo_failed_access_tokens_or_json_input(client):
    canary = 'hf_private_M7_secret_canary'
    response = client.post('/api/setup/download', json={'model_id': 'bad', 'access_token': canary * 20})
    assert response.status_code == 422 and canary not in response.text
    response = client.post('/api/setup/download', content='{"access_token":"' + canary, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422 and canary not in response.text
    denied = client.get('/api/state', headers={'Authorization': 'bad'})
    assert denied.status_code == 401 and denied.headers['cache-control'] == 'no-store'


def test_warm_citation_cache_detects_external_source_mutation_and_survives_restart(tmp_path):
    path = tmp_path / 'source.sqlite3'; store = Store(path)
    pid = store.create('Source')['projects'][0]['id']
    text = ('Alpha evidence\nBeta evidence\n' * 500).encode()
    doc = store.upload_document(pid, 'source.txt', text)
    parsed = parse_document('source.txt', text)
    store.commit_parsed(pid, doc['document_id'], doc['revision_id'], parsed)
    chunks = store.revision_chunks(pid, doc['revision_id'])
    for chunk in chunks:
        result = store.citation(pid, chunk['id']); loc = result['locator']
        unit = parsed['units'][loc['unit']]['text']
        assert loc['line_start'] == parsed['units'][loc['unit']]['locator']['line_start'] + unit[:loc['char_start']].count('\n')
    assert store._source_cache_bytes > 0
    with sqlite3.connect(path) as other:
        mutated = json.loads(json.dumps(parsed['units']))
        mutated[0]['text'] = mutated[0]['text'].replace('Alpha', 'Wrong')
        other.execute('UPDATE document_revisions SET units=? WHERE id=?', (json.dumps(mutated), doc['revision_id']))
    with pytest.raises(DomainError, match='source verification'): store.citation(pid, chunks[0]['id'])
    store.close(); store = Store(path)
    with pytest.raises(DomainError, match='source verification'): store.citation(pid, chunks[0]['id'])
    store.delete_document(pid, doc['document_id'])
    assert not store._source_cache and store._source_cache_bytes == 0
    store.close()


def test_source_cache_has_entry_and_byte_bounds(tmp_path, monkeypatch):
    import pm_copilot.document_store as module
    monkeypatch.setattr(module, 'SOURCE_CACHE_BYTES', 14000)
    store = Store(tmp_path / 'bounded.sqlite3'); pid = store.create('Bounds')['projects'][0]['id']
    for i in range(8):
        data = ('bounded evidence\n' * 300).encode()
        doc = store.upload_document(pid, f'{i}.txt', data)
        store.commit_parsed(pid, doc['document_id'], doc['revision_id'], parse_document(f'{i}.txt', data))
        store.citation(pid, store.revision_chunks(pid, doc['revision_id'])[0]['id'])
        assert len(store._source_cache) <= 4 and store._source_cache_bytes <= 14000
    store.close()
