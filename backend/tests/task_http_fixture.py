"""OpenAI HTTP responses for live-path tests; actual prompts and schemas choose responses."""
import json
from pathlib import Path
import httpx
from evals.task_fixtures import TaskModel


class TaskHTTPFixture:
    def __init__(self, path, *, fail=False, fail_after=None):
        self.path, self.fail = Path(path), fail
        self.model = TaskModel()
        self.calls, self.fail_after = 0, fail_after

    def __call__(self, request):
        body = json.loads(request.content)
        with self.path.open('a') as handle:
            handle.write(json.dumps(body, ensure_ascii=False) + '\n')
        self.calls += 1
        if self.fail or (self.fail_after is not None and self.calls > self.fail_after):
            return httpx.Response(403, json={'error': {'message': 'private provider failure', 'code': 'insufficient_quota'}})
        schema = body['response_format']['json_schema']['name']
        task = {'ResumeProfile':'document.parse_resume', 'JobProfile':'document.parse_jd',
                'MatchEvaluation':'evaluate_match', 'QuestionBlueprint':'plan_question_blueprint',
                'QuestionBatch':'generate_question_batch', 'AmbiguityFollowupSet':'generate_ambiguity_followups',
                'FollowUpAnalysisResponse':'followup.analyze_answer'}[schema]
        variables = {}
        if task == 'document.parse_resume':
            variables['chunks_json'] = json.loads(body['messages'][1]['content'].split('Resume chunks:\n', 1)[1])
        # Keep repeated question responses identical: live replay must not require stochastic variation.
        value = self.model.response(task, variables)
        return httpx.Response(200, json={'id':'local-http', 'object':'chat.completion', 'created':1,
            'model':body['model'], 'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(value)},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}})
