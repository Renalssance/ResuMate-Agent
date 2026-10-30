"""Budgeted raw OpenAI boundary for evals; prompts, validation and guards remain real."""
from collections import Counter
from copy import deepcopy
import os
from uuid import uuid4

from openai import OpenAI
from backend.model_transport import DefaultHttpxClient

from backend.agents.harness import AgentHarness


class LiveTaskModel:
    def __init__(self, config, recorder, *, transport=None):
        self.config, self.recorder = config, recorder
        self.calls, self.business_calls, self.hooks = [], [], {}
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY') or os.getenv('ARK_API_KEY'),
            base_url=os.getenv('OPENAI_BASE_URL') or os.getenv('BASE_URL'), max_retries=0,
            timeout=config.request_timeout_seconds,
            http_client=DefaultHttpxClient(follow_redirects=False, transport=transport))

    def close(self):
        self.client.close()

    def candidate_calls(self):
        return dict(Counter(call['candidate'] for call in self.business_calls if call['candidate']))

    def harness(self, *, user_id, guard=None, progress_callback=None):
        owner = self
        class Harness(AgentHarness):
            def __init__(self):
                # Eval configuration is already explicit and validated; never read a user's saved key.
                self.user_id, self.guard, self.progress_callback = user_id, guard, progress_callback
                self.model, self.base_url = owner.config.model, str(owner.client.base_url)
                self.max_tokens, self.request_timeout = owner.config.max_output_tokens, owner.config.request_timeout_seconds
                self.client = owner.client
                self.candidate = None

            def run_schema(self, *, task, variables, **kwargs):
                self.candidate = variables.get('resume_profile_json', {}).get('candidate_name')
                owner.business_calls.append({'task': task, 'candidate': self.candidate})
                return super().run_schema(task=task, variables=variables, **kwargs)

            def _create_chat_completion(self, task, messages, response_format, attempt, *, max_tokens=None):
                # The same production ownership/epoch guard precedes every actual send.
                if self.guard:
                    self.guard()
                call_id = str(uuid4())
                reserve = owner.recorder.reserve_call(call_id)
                request = {'model': self.model, 'messages': deepcopy(messages), 'temperature': 0.1,
                    owner.config.output_limit_parameter: owner.config.max_output_tokens,
                    'enable_thinking': owner.config.enable_thinking}
                if response_format is not None:
                    request['response_format'] = deepcopy(response_format)
                record = {'task': task, 'candidate': self.candidate, 'call_id': call_id,
                          'reflection_attempt': attempt, 'request': request}
                owner.calls.append(record)
                owner.recorder.start_call(call_id, reserved_cost=reserve,
                    **{key: value for key, value in record.items() if key != 'call_id'})
                kwargs = {key: value for key, value in request.items() if key != 'enable_thinking'}
                try:
                    response = self.client.chat.completions.create(**kwargs,
                        extra_body={'enable_thinking': owner.config.enable_thinking}, timeout=self.request_timeout)
                except Exception as error:
                    owner.recorder.on_llm_error(error, run_id=call_id)
                    raise
                tokens = response.usage
                usage = ({'input_tokens': tokens.prompt_tokens, 'output_tokens': tokens.completion_tokens}
                         if tokens is not None and type(tokens.prompt_tokens) is int and type(tokens.completion_tokens) is int
                         and tokens.prompt_tokens >= 0 and tokens.completion_tokens >= 0 else None)
                owner.recorder.settle_call(call_id, usage)
                public = {'text': response.choices[0].message.content or ''}
                record['public_output'] = public
                owner.recorder._finish(call_id, usage=usage, output=public)
                hook = owner.hooks.get(self.candidate or task)
                if hook:
                    hook()
                return response
        return Harness()
