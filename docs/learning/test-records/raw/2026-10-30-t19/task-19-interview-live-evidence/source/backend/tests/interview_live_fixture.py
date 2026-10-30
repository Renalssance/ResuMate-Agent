"""Subprocess-only synthetic OpenAI HTTP responses for the actual interview graph."""
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch

import httpx


def main(directory, scenario):
    from backend.tests.test_eval_budget import config
    from evals import run
    from evals.interview_runner import execute_interview_case
    from evals.records import write_json
    cases = [json.loads(line) for line in (run.ROOT / 'evals/cases/interviews.jsonl').read_text().splitlines()]
    case_id = {'cancel': 'interview-cancel-late-result', 'cancel-slow': 'interview-cancel-late-result',
        'cancel-budget': 'interview-cancel-late-result', 'eight': 'interview-eight-turn-limit',
        'replay': 'interview-command-replay', 'frozen': 'interview-frozen-submission',
        'memory': 'interview-feedback-memory'}.get(scenario, 'interview-followup')
    case = next(item for item in cases if item['id'] == case_id)
    if scenario == 'pages':
        case['input']['resume']['structured_data']['long_material'] = 'Synthetic frozen material line. ' * 450 + 'LONG_SOURCE_END'
    budget = config(max_case_model_calls=3 if scenario == 'cancel-budget' else 80, max_model_calls=80,
                    max_total_cost='0.1' if scenario == 'budget' else '3')
    count = 0
    delayed = False
    def respond(request):
        nonlocal count, delayed
        count += 1
        body = json.loads(request.content)
        with (directory / 'http.jsonl').open('a') as stream:
            stream.write(json.dumps(body, ensure_ascii=False) + '\n')
        if scenario == 'forbidden':
            return httpx.Response(403, json={'error': {'message': 'PRIVATE_PROVIDER_BODY', 'type': 'permission_error'}})
        messages = body['messages']
        system = '\n'.join(item['content'] if isinstance(item['content'], str) else '\n'.join(
            block.get('text', '') for block in item['content']) for item in messages if item['role'] == 'system')
        marker = '必保留业务上下文（摘要调用）\n' if '必保留业务上下文（摘要调用）\n' in system else '必保留业务上下文\n'
        required = json.loads(system.rsplit(marker, 1)[1])
        tools = {call['id']: call['function'] for item in messages for call in item.get('tool_calls', [])}
        context = None
        pages = {}
        for item in messages:
            call = tools.get(item.get('tool_call_id'))
            if call and call['name'] == 'get_interview_context':
                context = json.loads(item['content'])
            if call and call['name'] == 'read_file':
                args = json.loads(call['arguments'])
                text = re.split(r'^@@ lines [^\n]*@@\n', item['content'], maxsplit=1, flags=re.MULTILINE)[1]
                pages.setdefault(args['file_path'], {})[args.get('offset', 0)] = text
        name, args = 'get_interview_context', {}
        if context and context.get('format') == 'artifact_manifest':
            pending = next(((item, sum(len(text.splitlines()) for text in pages.get(item['path'], {}).values()))
                for item in context['artifacts'] if sum(len(text.splitlines()) for text in pages.get(item['path'], {}).values()) < item['lines']), None)
            if pending:
                name, args = 'read_file', {'file_path': pending[0]['path'], 'offset': pending[1], 'limit': 100}
            else:
                context = {'complete': True}
        if context and context.get('format') != 'artifact_manifest':
            turn = required['expectedTurn']
            ref = {'kind': 'resume', 'section': '/self_summary', 'quote': 'Built an API'} if turn == 0 else {
                'kind': 'answer', 'turnIndex': turn, 'quote': required['currentAnswer']['answer'][:120]}
            name, args = 'InterviewStep', {'feedback': None if turn == 0 else {
                'summary': 'Explain your actual validation steps.',
                'strengths': [{'text': 'Specific method.', 'refs': [ref]}],
                'improvements': [{'text': 'Explain failure handling.', 'refs': [ref]}],
                'practiceFocus': 'Practice explaining validation without inventing experience.'},
                'question': None if turn == 8 else {'text': 'Explain this cited experience.', 'mode': 'opening' if turn == 0 else 'follow_up', 'refs': [ref]}}
        if scenario == 'cancel-slow' and name == 'InterviewStep' and required['expectedTurn'] == 1 and not delayed:
            from threading import Event
            delayed = True
            Event().wait(16)
        message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'http-call-{count}',
            'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
        if '摘要调用' in marker:
            message = {'role': 'assistant', 'content': 'Use the original frozen source and accepted current answer.'}
        return httpx.Response(200, json={'id': f'completion-{count}', 'object': 'chat.completion', 'created': 1,
            'model': budget.model, 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': message}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}})
    original = run.make_live_model
    def make_model(config, recorder, case):
        return original(config, recorder, case, transport=httpx.MockTransport(respond))
    with patch.object(run, 'make_live_model', make_model):
        result = execute_interview_case({'case': case, 'mode': 'live', 'config': budget.public(), 'invocation': str(directory)})
    write_json(directory / 'result.json', result)


if __name__ == '__main__':
    main(Path(sys.argv[1]), sys.argv[2])
