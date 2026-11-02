"""Capture each LangChain model invocation, including tool rounds and summaries."""
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai.chat_models.base import _convert_message_to_dict
from backend.services.llm_calls import CallTrace


class ModelCallInspection(BaseCallbackHandler):
    run_inline = True

    def __init__(self, user_id, base_url, task, timeout):
        self.user_id, self.base_url, self.task, self.timeout = user_id, base_url, task, timeout
        self.calls = {}

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        params = dict(kwargs.get('invocation_params') or {})
        # LangChain reports stream=False here even for .stream(); omit that hint.
        params.pop('stream', None)
        params.update(messages=[_convert_message_to_dict(m) for m in messages[0]], timeout=self.timeout)
        self.calls[run_id] = CallTrace(self.user_id, self.task, self.base_url, params)

    def on_llm_new_token(self, token, *, run_id, chunk=None, **kwargs):
        trace = self.calls.get(run_id)
        if trace is None or chunk is None:
            return
        message = chunk.message
        trace.add_chunk({'choices': [{'index': 0, 'delta': {
            'content': message.content if isinstance(message.content, str) else '',
            'reasoning_content': message.additional_kwargs.get('reasoning_content', ''),
            'tool_calls': message.additional_kwargs.get('tool_calls', []),
        }, 'finish_reason': (chunk.generation_info or {}).get('finish_reason')}]})

    def on_llm_end(self, response, *, run_id, **kwargs):
        trace = self.calls.pop(run_id, None)
        if trace is None:
            return
        choices, usage = [], None
        for batch in response.generations:
            for generation in batch:
                message = generation.message
                choices.append({'message': _convert_message_to_dict(message),
                    'finish_reason': (generation.generation_info or {}).get('finish_reason')
                        or message.response_metadata.get('finish_reason')})
                # Preserve provider reasoning as well as content and tool calls.
                if message.additional_kwargs.get('reasoning_content'):
                    choices[-1]['message']['reasoning_content'] = message.additional_kwargs['reasoning_content']
                if message.usage_metadata:
                    metadata = message.usage_metadata
                    usage = {'prompt_tokens': metadata['input_tokens'], 'completion_tokens': metadata['output_tokens'],
                             'total_tokens': metadata['total_tokens'],
                             'completion_tokens_details': metadata.get('output_token_details', {})}
        if usage is None:
            usage = (response.llm_output or {}).get('token_usage')
        trace.finish(response={'choices': choices, 'usage': usage})

    def on_llm_error(self, error, *, run_id, **kwargs):
        trace = self.calls.pop(run_id, None)
        if trace:
            trace.finish(error=error)
