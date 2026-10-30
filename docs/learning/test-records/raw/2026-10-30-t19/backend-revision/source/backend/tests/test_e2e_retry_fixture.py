"""The browser's one retry example must survive bounded parser processes."""
import json
import os
from pathlib import Path
import subprocess
import sys


MODEL_RESPONSES = r'''
import json
import sys
import httpx
from backend.tests import e2e_legacy_fixture as fixture

fixture._context.set({'task': 'document.parse_jd', 'variables': {}})
request = httpx.Request('POST', 'https://model.example/v1/chat/completions', json={
    'model': 'synthetic',
    'messages': [{'role': 'system', 'content': 'synthetic'},
                 {'role': 'user', 'content': sys.argv[1]}],
})
print(json.dumps([fixture.model_response(request).status_code for _ in range(int(sys.argv[2]))]))
'''


def test_retry_example_succeeds_in_the_next_document_process(tmp_path):
    env = {**os.environ, 'RESUMATE_E2E_ROOT': str(tmp_path)}

    def responses(prompt, count):
        result = subprocess.run(
            [sys.executable, '-c', MODEL_RESPONSES, prompt, str(count)],
            cwd=Path(__file__).resolve().parents[2], env=env,
            check=True, capture_output=True, text=True, timeout=15,
        )
        return json.loads(result.stdout.strip().splitlines()[-1])

    prompt = 'E2E_RETRY_PARSE 负责 API 和数据库设计。'
    assert responses(prompt, 3) == [503, 503, 503]
    assert responses(prompt, 1) == [200]
    assert responses('E2E_ALWAYS_FAIL 负责 API 设计。', 1) == [503]
    assert responses('负责 API 和数据库设计。', 1) == [200]
