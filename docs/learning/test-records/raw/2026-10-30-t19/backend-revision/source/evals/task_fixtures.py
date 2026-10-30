"""Synthetic structured responses for durable-task evaluations; no provider client."""
from collections import Counter
import json


JOB_PROFILE = {'job_title': 'API Engineer', 'summary': 'Build APIs', 'criteria': [
    {'criterion_id': 'api', 'name': 'API', 'description': 'Build APIs', 'importance': 'must', 'weight': 100, 'evidence_query': 'API'}]}


class TaskModel:
    def __init__(self):
        self.calls = []
        self.hooks = {}
        self.label = 'Original question'

    def harness(self, *, user_id, guard=None, progress_callback=None):
        owner = self
        class Harness:
            def __init__(self):
                self.guard = guard

            def run_schema(self, *, task, schema, variables, **kwargs):
                if guard:
                    guard()
                candidate = variables.get('resume_profile_json', {}).get('candidate_name')
                owner.calls.append({'task': task, 'candidate': candidate})
                hook = owner.hooks.get(candidate or task)
                if hook:
                    hook()
                return schema.model_validate(owner.response(task, variables))
        return Harness()

    def candidate_calls(self):
        return dict(Counter(call['candidate'] for call in self.calls if call['candidate']))

    def question(self, text):
        return dict(question=text, question_type='gap_validation', difficulty='medium', assessment_points=['API evidence'],
                    related_criteria=['api'], evidence_chunk_ids=[], reference_answer_direction='Explain actual responsibility',
                    scoring_rubric=['Concrete evidence'], suggested_followups=['How was it verified?'])

    def response(self, task, variables):
        if task == 'document.parse_jd':
            return JOB_PROFILE
        if task == 'document.parse_resume':
            chunk = variables['chunks_json'][0]
            return {'candidate_name': 'Parsed Candidate', 'self_summary': self.label, 'source_refs': [
                {key: chunk[key] for key in ('chunk_id', 'page_number', 'section', 'text')}]}
        if task == 'evaluate_match':
            return {'evaluations': [dict(criterion_id='api', name='API', weight=100, score=0, status='no_evidence',
                reason='Need concrete citation', evidence_chunk_ids=[], missing_evidence=['API evidence'], risk='')]}
        if task == 'plan_question_blueprint':
            return {'formal_questions': [dict(question_id='q1', question_type='gap_validation',
                primary_criterion_id='api', objective='Verify API experience', difficulty='medium')]}
        if task == 'generate_question_batch':
            return {'formal_questions': [self.question(self.label)]}
        if task == 'generate_ambiguity_followups':
            return {'ambiguity_followups': [self.question(f'Clarify {i}') for i in range(3)]}
        if task == 'followup.analyze_answer':
            return dict(follow_up=self.label, reason='Need concrete evidence', evidence=[], risks=[],
                        current_ability='Pending verification', next_suggestion='Give an example')
        raise ValueError('Unsupported synthetic task')


class TaskEmbedding:
    contract = {'provider': 'eval-fixture', 'model': 'deterministic-four-dimensions'}
    def embed(self, text):
        return [float(text.casefold().count(word) + 1) for word in ('api', 'test', 'candidate', 'field')]
    def embed_many(self, texts):
        return [self.embed(text) for text in texts]
