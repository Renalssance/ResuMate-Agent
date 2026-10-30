"""The opt-in crash experiment must use this host and the selected fresh image."""
import json
from pathlib import Path
import runpy
import subprocess
from unittest.mock import patch


RECOVERY = Path(__file__).with_name('test_agent_recovery.py')


def load_recovery(docker):
    with patch('shutil.which', return_value=docker):
        return runpy.run_path(str(RECOVERY))


def test_recovery_uses_docker_from_path():
    assert load_recovery('/usr/bin/docker')['DOCKER'] == '/usr/bin/docker'


def test_recovery_retains_docker_desktop_fallback():
    assert load_recovery(None)['DOCKER'] == '/Applications/Docker.app/Contents/Resources/bin/docker'


def test_recovery_evidence_records_selected_image_and_actual_head(tmp_path, monkeypatch):
    module = load_recovery('/usr/bin/docker')
    context = tmp_path / 'context.json'
    context.write_text(json.dumps({'invocation_id': 'portable-test', 'cases': [
        {'id': case_id, 'input': {}} for case_id in module['CASE_IDS']]}))
    evidence = tmp_path / 'evidence.json'
    monkeypatch.setenv('RESUMATE_RECOVERY_CONTEXT', str(context))
    monkeypatch.setenv('RESUMATE_RECOVERY_EVIDENCE', str(evidence))
    monkeypatch.setenv('RESUMATE_RECOVERY_IMAGE', 'resumate-ci-backend:latest')
    generator = module['recovery_context'].__wrapped__()
    try:
        _, root, snapshot, _, _, _ = next(generator)
        source = json.loads(evidence.read_text())['source']
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        assert {key: source[key] for key in ('base_commit', 'image')} == {
            'base_commit': head, 'image': 'resumate-ci-backend:latest'}
        assert (snapshot / 'backend' / 'worker_tasks.py').is_file()
    finally:
        generator.close()
