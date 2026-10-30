"""Print only a confirmed version's frozen material; SQL owns download visibility."""
from copy import deepcopy
from datetime import timezone
import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.agent_models import AgentRun
from backend.db.career_models import ResumeVersion
from backend.db.database import SessionLocal
from backend.schemas.agent_runs import RunStatus
from backend.schemas.resume_versions import VersionStatus
from backend.services import agent_runs
from backend.services.agent_runs import RunError
from backend.services.run_events import append_event

logger = logging.getLogger(__name__)


def read_confirmed_version(db: Session, user_id: int, version_id: str,
                           *, revision: int | None = None) -> ResumeVersion:
    version = db.scalar(select(ResumeVersion).where(
        ResumeVersion.id == version_id, ResumeVersion.user_id == user_id))
    if version is None:
        raise RunError(404, 'not_found', '简历版本不存在')
    if version.status != VersionStatus.CONFIRMED:
        raise RunError(409, 'version_not_confirmed', '请先审阅并确认简历版本')
    if revision is not None and version.revision != revision:
        raise RunError(409, 'input_changed', '已确认版本已变化，请重新导出')
    return version


def build_template_data(structured_content: dict) -> dict:
    resume = deepcopy(structured_content['resume'])
    # A deliberately empty self_summary must never revive the old summary field.
    resume['display_summary'] = resume.get('self_summary', resume.get('summary', ''))
    edited = {change['section'] for change in structured_content.get('changes', [])
              if change.get('status') in ('accepted', 'edited')}
    for section in ('work_experience', 'projects'):
        for index, item in enumerate(resume.get(section, [])):
            item['display_bullets'] = []
            if f'/{section}/{index}/description' in edited:
                continue
            description = item.get('description', '')
            for bullet in item.get('bullets', []):
                text = bullet.get('raw_text') or bullet.get('action', '')
                if text and text not in description and text not in item['display_bullets']:
                    item['display_bullets'].append(text)
            for metric in item.get('metrics', []):
                text = metric.get('raw_text') or ' '.join(part for part in (
                    metric.get('name', ''), metric.get('value', '') + metric.get('unit', '')) if part)
                if text and text not in description and not any(
                        text in bullet for bullet in item['display_bullets']):
                    item['display_bullets'].append(text)
    for section in ('skills', 'achievements'):
        resume[section] = [{'name': item} if isinstance(item, str) else item
                           for item in resume.get(section, [])]
    return resume


def render_html(structured_content: dict) -> str:
    from jinja2 import Environment, FileSystemLoader
    environment = Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1] / 'templates'),
                              autoescape=True, trim_blocks=True, lstrip_blocks=True)
    return environment.get_template('resume.html').render(resume=build_template_data(structured_content))


def render_pdf(structured_content: dict, output_path: Path) -> None:
    from playwright.sync_api import sync_playwright
    html = render_html(structured_content)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(java_script_enabled=False)
            try:
                context.route('**/*', lambda route: route.abort())
                page = context.new_page()
                page.set_content(html, wait_until='load')
                page.emulate_media(media='print')
                page.evaluate('document.fonts.ready')
                page.pdf(path=str(output_path), format='A4', print_background=True,
                         prefer_css_page_size=True)
            finally:
                context.close()
        finally:
            browser.close()


def export_path(run_id: str) -> Path:
    return Path(os.getenv('RESUME_EXPORT_DIR', 'data/exports')) / f'{run_id}.pdf'


def pdf_artifact(run: AgentRun) -> dict | None:
    if run.kind != 'resume_export' or run.status != RunStatus.SUCCEEDED:
        return None
    expected = {'type': 'resume_pdf', 'id': run.id,
                'resumeVersionId': run.input_json['resumeVersionId'],
                'revision': run.input_versions['resumeVersion']}
    if expected not in run.output_refs:
        return None
    return {'kind': 'resume_pdf', 'id': run.id, 'runId': run.id,
            'resumeVersionId': expected['resumeVersionId'], 'revision': expected['revision'],
            'filename': f"简历-第{expected['revision']}版.pdf",
            'downloadUrl': f'/api/agent/runs/{run.id}/download',
            'createdAt': run.updated_at.replace(tzinfo=timezone.utc).isoformat()}


def download_file(db: Session, user_id: int, run_id: str) -> tuple[Path, str]:
    run = agent_runs.get_run(db, user_id, run_id)
    artifact = pdf_artifact(run)
    if artifact is None:
        raise RunError(409, 'artifact_not_ready', 'PDF 尚未成功生成')
    path = export_path(run.id)
    if not path.is_file():
        raise RunError(404, 'artifact_missing', 'PDF 文件不存在，请重新导出')
    return path, artifact['filename']


def run_resume_export(run_id: str, epoch: int) -> None:
    temporary = None
    try:
        with SessionLocal() as db:
            agent_runs.guard_execution(db, run_id, epoch)
            run = db.get(AgentRun, run_id)
            version = read_confirmed_version(db, run.user_id, run.input_json['resumeVersionId'],
                                             revision=run.input_versions['resumeVersion'])
            content = deepcopy(version.structured_content)
            output_ref = {'type': 'resume_pdf', 'id': run_id,
                          'resumeVersionId': version.id, 'revision': version.revision}
            # Release the guard's write lock before starting Chromium.
            db.commit()
        target = export_path(run_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f'.{run_id}.tmp.pdf')
        render_pdf(content, temporary)
        with SessionLocal() as db:
            agent_runs.guard_execution(db, run_id, epoch)
            temporary.replace(target)
            append_event(db, run_id, 'artifact.created', {'artifact_id': run_id, 'kind': 'resume_pdf'})
            agent_runs.finish_run(db, run_id, epoch, RunStatus.SUCCEEDED, output_refs=[output_ref])
    except Exception as error:
        code = error.code if isinstance(error, RunError) else 'pdf_export_failed'
        with SessionLocal() as db:
            agent_runs.finish_run(db, run_id, epoch, RunStatus.FAILED, error_code=code)
        logger.warning('PDF export %s stopped (%s)', run_id, code)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
