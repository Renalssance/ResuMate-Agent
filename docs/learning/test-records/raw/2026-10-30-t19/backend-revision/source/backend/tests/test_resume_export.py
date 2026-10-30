"""Confirmed material exports never re-read mutable input or enter the model."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from backend.db.agent_models import AgentRun, AgentRunEvent, AgentSession
from backend.db.career_models import ResumeVersion
from backend.db.models import JobDescription, Resume
from backend.schemas.agent_runs import RunCreate, RunStatus
from backend.services import agent_runs
from backend.tests.career_fixtures import career_engine, career_db
from backend.tests.test_agent_run_routes import run_client, headers


@pytest.fixture
def confirmed(career_db):
    version = ResumeVersion(id=str(uuid4()), user_id=1, resume_id=1, jd_id=1,
        revision=3, status='confirmed', structured_content={'resume': {
            'candidate_name': '林晓', 'self_summary': '确认后的接口开发经历'}, 'changes': []})
    career_db.add(version)
    career_db.commit()
    return version


@pytest.fixture(autouse=True)
def offline_delivery(monkeypatch):
    monkeypatch.setattr('backend.routes.agent_runs.publish_run', lambda run_id: False)
    # The convenience route is added by this unit; keep the red schema/API run possible.
    import backend.routes.resume_versions as routes
    if hasattr(routes, 'publish_run'):
        monkeypatch.setattr(routes, 'publish_run', lambda run_id: False)


def export_request(version_id, request_id='export-1'):
    return RunCreate(kind='resume_export', resumeVersionId=version_id, requestId=request_id)


@pytest.mark.parametrize('payload', [
    {'kind': 'resume_export', 'resumeVersionId': 'version', 'jdId': 1},
    {'kind': 'resume_export', 'resumeVersionId': 'version', 'resumeId': 1},
    {'kind': 'resume_export'},
    {'kind': 'tailoring', 'jdId': 1, 'resumeId': 1, 'resumeVersionId': 'version'},
    {'kind': 'tailoring', 'jdId': 1},
    {'kind': 'unknown', 'resumeVersionId': 'version'},
])
def test_kind_rejects_missing_or_mixed_inputs(payload):
    with pytest.raises(ValidationError):
        RunCreate(**payload, requestId='validation')


def test_export_captures_only_confirmed_version_and_reuses_request(confirmed, career_db, run_client):
    response = run_client.post('/api/agent/runs', headers=headers(), json={
        'kind': 'resume_export', 'resumeVersionId': confirmed.id, 'requestId': 'export-1'})
    assert response.status_code == 202, response.text
    run_id = response.json()['runId']
    repeated = run_client.post(f'/api/resume-versions/{confirmed.id}/export',
                              headers=headers(), json={'requestId': 'export-1'})
    assert repeated.status_code == 202, repeated.text
    assert repeated.json() == response.json()
    career_db.rollback()
    run = career_db.get(AgentRun, run_id)
    assert run.input_json == {'resumeVersionId': confirmed.id}
    assert run.input_versions == {'resumeVersion': 3}
    snapshot = run_client.get(f'/api/agent/runs/{run_id}', headers=headers()).json()
    assert snapshot['input'] == {'resumeVersionId': confirmed.id}
    assert run_client.get('/api/agent/runs', headers=headers()).json()['items'][0]['input'] == snapshot['input']
    conflict = run_client.post('/api/agent/runs', headers=headers(), json={
        'kind': 'resume_export', 'resumeVersionId': 'other', 'requestId': 'export-1'})
    assert conflict.status_code == 409 and conflict.json()['code'] == 'request_conflict'
    assert career_db.query(AgentRun).count() == 1


def test_draft_and_foreign_versions_are_not_exportable(confirmed, career_db, run_client):
    url = f'/api/resume-versions/{confirmed.id}/export'
    assert run_client.post(url, headers=headers('bob'), json={'requestId': 'foreign'}).status_code == 404
    assert run_client.post(url, json={'requestId': 'no-auth'}).status_code == 401
    confirmed.status = 'draft'
    career_db.commit()
    response = run_client.post(url, headers=headers(), json={'requestId': 'draft'})
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'version_not_confirmed'
    assert career_db.query(AgentRun).count() == 0


def test_retry_uses_frozen_version_after_main_documents_deleted(confirmed, career_db):
    run = agent_runs.create_run(career_db, 1, export_request(confirmed.id))
    run_id = run.id
    epoch = agent_runs.claim_run(career_db, run_id)
    agent_runs.finish_run(career_db, run_id, epoch, RunStatus.FAILED, error_code='pdf_export_failed')
    career_db.delete(career_db.get(Resume, 1))
    career_db.delete(career_db.get(JobDescription, 1))
    career_db.commit()
    retried = agent_runs.retry_run(career_db, 1, run_id)
    assert retried.status == 'queued' and retried.attempt == 2
    assert retried.input_versions == {'resumeVersion': 3}
    assert retried.input_json == {'resumeVersionId': confirmed.id}


def test_retry_refuses_changed_frozen_revision(confirmed, career_db):
    run = agent_runs.create_run(career_db, 1, export_request(confirmed.id))
    epoch = agent_runs.claim_run(career_db, run.id)
    agent_runs.finish_run(career_db, run.id, epoch, RunStatus.FAILED, error_code='pdf_export_failed')
    confirmed.revision += 1
    career_db.commit()
    with pytest.raises(agent_runs.RunError) as error:
        agent_runs.retry_run(career_db, 1, run.id)
    assert error.value.code == 'input_changed'


def template_content():
    return {'resume': {
        'candidate_name': '林晓<script>alert(1)</script>',
        'contact': {'email': 'lin@example.test', 'website': 'https://example.test/作品'},
        'self_summary': '', 'summary': '不应恢复的旧简介',
        'education': [{'school': '示例大学', 'college': '计算机学院', 'major': '软件工程',
            'degree': '硕士', 'years': '2020—2023', 'gpa': '3.8/4.0', 'rank': '前5%',
            'lab': '系统实验室', 'research_direction': '分布式系统', 'advisor': '张老师',
            'papers': ['系统可靠性论文'], 'courses': ['高级数据库'], 'achievements': ['优秀毕业生']}],
        'work_experience': [{'company': '示例公司', 'title': '工程师', 'duration': '2023—至今',
            'description': '本人确认的经历', 'bullets': [{'raw_text': '被替代的原经历'}],
            'technologies': ['Python', 'SQL']},
            {'company': '未修改公司', 'description': '保留的简介',
             'bullets': [{'raw_text': '保留的简介'}, {'raw_text': '独立工作要点'}]}],
        'projects': [{'name': '清空项目', 'role': '开发者', 'description': '',
                      'bullets': [{'raw_text': '不应复活的项目要点'}]},
                     {'name': '未修改项目', 'description': '项目简介', 'duration': '2022',
                      'bullets': [{'raw_text': '独立项目要点'}], 'technologies': ['FastAPI']}],
        'skills': [{'name': 'PostgreSQL', 'category': '数据库', 'proficiency_claim': '熟练'}, 'Git'],
        'achievements': [{'name': '算法竞赛', 'level': '省级', 'category': '一等奖'}, '优秀奖'],
        'certifications': ['数据库认证'], 'languages': ['英语 CET-6'],
        'source_refs': ['不可打印的来源'], 'quality': {'note': '不可打印的质量备注'},
    }, 'changes': [
        {'section': '/work_experience/0/description', 'status': 'accepted', 'reason': '不可打印的审阅理由'},
        {'section': '/projects/0/description', 'status': 'edited', 'editedText': ''},
    ]}


def test_template_preserves_supported_fields_and_honors_reviewed_descriptions():
    from backend.services import resume_export
    content = template_content()
    before = deepcopy(content)
    html = resume_export.render_html(content)
    for text in ['示例大学', '计算机学院', '软件工程', '硕士', '2020—2023', '3.8/4.0', '前5%',
                 '系统实验室', '分布式系统', '张老师', '系统可靠性论文', '高级数据库', '优秀毕业生',
                 '示例公司', '工程师', '2023—至今', '本人确认的经历', 'Python', 'SQL',
                 '独立工作要点', '未修改项目', '项目简介', '2022', '独立项目要点', 'FastAPI',
                 'PostgreSQL', '数据库', '熟练', 'Git', '算法竞赛', '省级', '一等奖', '优秀奖',
                 '数据库认证', '英语 CET-6', 'lin@example.test', 'https://example.test/作品']:
        assert text in html, text
    for text in ['不应恢复的旧简介', '被替代的原经历', '不应复活的项目要点',
                 '不可打印的来源', '不可打印的质量备注', '不可打印的审阅理由']:
        assert text not in html, text
    assert html.count('保留的简介') == 1
    assert '<script>' not in html and '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<a ' not in html
    assert content == before


def test_template_supports_summary_and_dates_without_shadow_fields():
    from backend.services import resume_export
    html = resume_export.render_html({'resume': {'candidate_name': '陈明', 'summary': '历史摘要',
        'education': [{'school': '测试大学', 'start_date': '2016年', 'end_date': '2020年'}],
        'work_experience': [{'company': '测试公司', 'start_date': '2020年', 'end_date': '至今'}]}})
    assert all(text in html for text in ['历史摘要', '2016年', '2020年', '至今'])


def test_real_renderer_prints_text_pdf(tmp_path):
    import pymupdf
    from backend.services import resume_export
    path = tmp_path / 'resume.pdf'
    resume_export.render_pdf({'resume': {'candidate_name': 'Lin', 'self_summary': 'Frozen confirmed resume'}}, path)
    with pymupdf.open(path) as document:
        assert len(document) == 1
        assert 'Frozen confirmed resume' in document[0].get_text()
        assert document[0].rect.width == pytest.approx(595, abs=1)


@pytest.fixture
def export_runtime(career_engine, tmp_path, monkeypatch):
    from backend.services import resume_export
    from backend import worker_tasks
    factory = sessionmaker(bind=career_engine, expire_on_commit=False)
    monkeypatch.setenv('RESUME_EXPORT_DIR', str(tmp_path / 'exports'))
    monkeypatch.setenv('AGENT_STATE_DIR', str(tmp_path / 'agent'))
    monkeypatch.setattr(resume_export, 'SessionLocal', factory, raising=False)
    monkeypatch.setattr(worker_tasks, 'SessionLocal', factory)
    return resume_export, worker_tasks, tmp_path / 'exports'


def test_worker_exports_frozen_material_without_model_and_exposes_owned_download(
        confirmed, career_db, career_engine, run_client, export_runtime, monkeypatch):
    service, worker, directory = export_runtime
    from backend.agent_runtime import runner
    def no_model(*args, **kwargs):
        pytest.fail('PDF export entered the model runner')
    monkeypatch.setattr(runner, 'run_agent', no_model)
    version_id = confirmed.id
    run_id = agent_runs.create_run(career_db, 1, export_request(version_id)).id
    career_db.delete(career_db.get(Resume, 1))
    career_db.commit()
    def print_frozen(content, target):
        assert content['resume']['self_summary'] == '确认后的接口开发经历'
        assert target.name == f'.{run_id}.tmp.pdf'
        # A separate writer must work while the slow browser print is active.
        with Session(career_engine) as db:
            assert agent_runs.heartbeat_run(db, run_id, 1)
        target.write_bytes(b'%PDF-frozen-material')
    monkeypatch.setattr(service, 'render_pdf', print_frozen, raising=False)
    worker.execute_run.run(run_id)
    snapshot = run_client.get(f'/api/agent/runs/{run_id}', headers=headers()).json()
    assert snapshot['status'] == 'succeeded', snapshot
    assert snapshot['outputRefs'] == [{'type': 'resume_pdf', 'id': run_id,
                                      'resumeVersionId': version_id, 'revision': 3}]
    artifacts = run_client.get(f'/api/agent/runs/{run_id}/artifacts', headers=headers()).json()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert {key: artifact[key] for key in ('kind', 'id', 'runId', 'resumeVersionId', 'revision')} == {
        'kind': 'resume_pdf', 'id': run_id, 'runId': run_id, 'resumeVersionId': version_id, 'revision': 3}
    assert artifact['downloadUrl'] == f'/api/agent/runs/{run_id}/download'
    assert artifact['filename'].endswith('.pdf') and artifact['createdAt'].endswith('+00:00')
    response = run_client.get(artifact['downloadUrl'], headers=headers())
    assert response.status_code == 200 and response.content == b'%PDF-frozen-material'
    assert response.headers['content-type'] == 'application/pdf'
    assert 'attachment' in response.headers['content-disposition']
    assert run_client.get(artifact['downloadUrl'], headers=headers('bob')).status_code == 404
    assert run_client.get(artifact['downloadUrl']).status_code == 401
    career_db.rollback()
    assert career_db.get(AgentSession, snapshot['sessionId']).active_run_id is None
    events = career_db.query(AgentRunEvent).filter_by(run_id=run_id, type='artifact.created').all()
    assert [event.payload for event in events] == [{'artifact_id': run_id, 'kind': 'resume_pdf'}]
    assert list(directory.iterdir()) == [directory / f'{run_id}.pdf']
    (directory / f'{run_id}.pdf').unlink()
    missing = run_client.get(artifact['downloadUrl'], headers=headers())
    assert missing.status_code == 404 and missing.json()['code'] == 'artifact_missing'


@pytest.mark.parametrize('outcome', ['cancel', 'failure', 'lost'])
def test_incomplete_export_never_exposes_file_or_success_event(
        confirmed, career_db, career_engine, run_client, export_runtime, monkeypatch, outcome):
    service, _, directory = export_runtime
    run_id = agent_runs.create_run(career_db, 1, export_request(confirmed.id)).id
    epoch = agent_runs.claim_run(career_db, run_id)
    def interrupted_print(content, path):
        path.write_bytes(b'%PDF-incomplete')
        if outcome == 'failure':
            raise RuntimeError('Browser unavailable')
        with Session(career_engine) as db:
            if outcome == 'cancel':
                agent_runs.cancel_run(db, 1, run_id)
            else:
                run = db.get(AgentRun, run_id)
                run.execution_epoch += 1
                db.commit()
    monkeypatch.setattr(service, 'render_pdf', interrupted_print, raising=False)
    service.run_resume_export(run_id, epoch)
    snapshot = run_client.get(f'/api/agent/runs/{run_id}', headers=headers()).json()
    assert snapshot['status'] == {'cancel': 'cancelled', 'failure': 'failed', 'lost': 'running'}[outcome]
    assert snapshot['outputRefs'] == []
    if outcome == 'failure':
        assert snapshot['errorCode'] == 'pdf_export_failed' and snapshot['attempt'] == 1
    assert run_client.get(f'/api/agent/runs/{run_id}/artifacts', headers=headers()).json() == []
    assert run_client.get(f'/api/agent/runs/{run_id}/download', headers=headers()).status_code == 409
    career_db.rollback()
    assert career_db.query(AgentRunEvent).filter_by(run_id=run_id, type='artifact.created').count() == 0
    assert list(directory.glob('*.pdf')) == []


def test_unknown_worker_kind_fails_explicitly(confirmed, career_db, export_runtime, monkeypatch):
    _, worker, _ = export_runtime
    from backend.agent_runtime import runner
    def no_model(*args, **kwargs):
        pytest.fail('Unknown kind entered the model runner')
    monkeypatch.setattr(runner, 'run_agent', no_model)
    run = agent_runs.create_run(career_db, 1, export_request(confirmed.id))
    run.kind = 'unsupported'
    career_db.commit()
    run_id = run.id
    worker.execute_run.run(run_id)
    career_db.rollback()
    run = career_db.get(AgentRun, run_id)
    assert run.status == 'failed' and run.error_code == 'unsupported_run_kind'


def test_template_prints_independent_metrics_without_reviving_reviewed_claims():
    from backend.services.resume_export import render_html
    html = render_html({'resume': {'candidate_name': '林晓', 'work_experience': [
        {'company': '示例公司', 'bullets': [{'raw_text': '使用Docker和K8s建设部署流程'}],
         'metrics': [{'name': '吞吐', 'value': '3倍'}, {'raw_text': '减少人工耗时 10 小时'},
                     {'raw_text': '使用Docker和K8s建设部署流程'}]},
        {'company': '审阅公司', 'description': '本人确认的工作',
         'metrics': [{'raw_text': '旧工作成果不应恢复'}]},
    ], 'projects': [
        {'name': '独立成果项目', 'description': '请求延迟降低 20%',
         'metrics': [{'raw_text': '请求延迟降低 20%'}, {'name': '月均用户', 'value': '800', 'unit': '人'}]},
        {'name': '清空成果项目', 'description': '', 'metrics': [{'name': '旧项目成果', 'value': '99%'}]},
    ]}, 'changes': [
        {'section': '/work_experience/1/description', 'status': 'accepted'},
        {'section': '/projects/1/description', 'status': 'edited', 'editedText': ''},
    ]})
    for text in ['吞吐', '3倍', '减少人工耗时 10 小时', '月均用户', '800', '人']:
        assert text in html, text
    assert html.count('使用Docker和K8s建设部署流程') == 1
    assert html.count('请求延迟降低 20%') == 1
    assert '旧工作成果不应恢复' not in html and '旧项目成果' not in html
