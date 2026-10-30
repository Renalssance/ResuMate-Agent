"""Diagnose real SDK failures without retaining provider text or credentials."""
import json

import httpx
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, BadRequestError
import pytest

from evals.records import CallRecorder


@pytest.mark.parametrize('failure,expected_type,http_status', [
    ('http', BadRequestError, 400),
    ('connection', APIConnectionError, None),
])
def test_error_records_preserve_type_and_status_without_provider_body(tmp_path, failure, expected_type, http_status):
    def respond(request):
        if failure == 'connection':
            raise httpx.ConnectError('private transport diagnostic', request=request)
        return httpx.Response(400, json={'error': {
            'message': 'private provider diagnostic', 'type': 'invalid_request_error', 'code': 'private-provider-code'}},
            request=request)

    path = tmp_path / 'calls.jsonl'
    recorder = CallRecorder(path, case_id='error-diagnostic', model='synthetic')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model = ChatOpenAI(model='synthetic', api_key='private-api-key', base_url='https://synthetic.invalid/v1',
                           http_client=client, max_retries=0, callbacks=[recorder])
        with pytest.raises(expected_type):
            model.invoke('synthetic input')
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 2
    failure_record = records[-1]
    assert failure_record['event'] == 'failed'
    assert failure_record['error_code'] == 'model_call_failed'
    assert failure_record['error_type'] == expected_type.__name__
    assert failure_record['http_status'] == http_status
    assert failure_record['usage'] is None
    assert 'private' not in path.read_text()
