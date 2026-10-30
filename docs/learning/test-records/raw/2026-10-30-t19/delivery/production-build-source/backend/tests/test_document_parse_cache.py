from types import SimpleNamespace

from backend.db.agent_models import AgentRun
from backend.db.models import LlmUsageEvent
from backend.tests.career_fixtures import career_db, career_engine
from backend.tests.test_document_tasks import parse_app, upload, execute


def test_upload_reuses_structured_data_for_same_file_hash(parse_app, monkeypatch):
    client, factory, originals = parse_app
    calls, indexed = [], []
    parsed = {'candidate_name': 'Ada Lovelace', 'name': 'Ada Lovelace'}
    def parse(*args, **kwargs):
        calls.append(1)
        return parsed
    rag = SimpleNamespace(replace_document_chunks=lambda **kw: indexed.append(kw['document_id']))
    ids, results = [], []
    for key in ['first', 'second']:
        run_id = upload(client, key).json()['taskId']
        execute(factory, run_id, monkeypatch, parse=parse, rag=rag)
        with factory() as db:
            result = db.get(AgentRun, run_id).result_json['documents'][0]
            ids.append(result['id'])
            results.append(result['parsed_content'])
    assert calls == [1]
    assert results == [parsed, parsed]
    assert ids[0] != ids[1]
    assert indexed == [int(value.split(':')[1]) for value in ids]


def test_upload_releases_write_transaction_before_llm_usage_recording(parse_app, monkeypatch):
    client, factory, originals = parse_app
    def parse(*args, **kwargs):
        with factory() as usage_db:
            usage_db.add(LlmUsageEvent(user_id=1, task='document.parse_resume', model='model', base_url='base',
                prompt_tokens=1, completion_tokens=1, total_tokens=2, success=True, error_type='', elapsed_ms=1))
            usage_db.commit()
        return {'candidate_name': 'Ada'}
    run_id = upload(client).json()['taskId']
    execute(factory, run_id, monkeypatch, parse=parse)
    with factory() as db:
        assert db.get(AgentRun, run_id).status == 'succeeded'
        assert db.query(LlmUsageEvent).count() == 1
