"""Retain the reasoning_content field returned by the configured compatible provider."""
from langchain_openai import ChatOpenAI


class ReasoningChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        result = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        choices = chunk.get('choices') or []
        if result is not None and choices:
            reasoning = (choices[0].get('delta') or {}).get('reasoning_content')
            if reasoning:
                result.message.additional_kwargs['reasoning_content'] = reasoning
        return result
