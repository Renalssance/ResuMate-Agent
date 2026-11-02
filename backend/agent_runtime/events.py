"""Translate public SDK messages to the durable, minimal business event contract."""
from time import monotonic

from langchain_core.messages import AIMessage
from sqlalchemy import select

from backend.db.agent_models import AgentRunEvent
from backend.services.agent_runs import guard_execution
from backend.services.run_events import append_event


class RuntimeEvents:
    def __init__(self, run_id, epoch, session_factory, *, include_reasoning=False):
        self.run_id = run_id
        self.epoch = epoch
        self.session_factory = session_factory
        self.text = ''
        self.include_reasoning = include_reasoning
        self.reasoning = ''
        self.reasoning_active = False
        self.last_flush = monotonic()

    def message(self, message, metadata):
        # Other nodes can run internal summarization models. Never publish their text.
        if not isinstance(message, AIMessage) or metadata.get('langgraph_node') != 'model':
            return
        content = message.content
        text = content if isinstance(content, str) else ''.join(
            block if isinstance(block, str) else block.get('text', '')
            for block in content if isinstance(block, str) or block.get('type') == 'text')
        reasoning = message.additional_kwargs.get('reasoning_content', '') if self.include_reasoning else ''
        if reasoning:
            self.reasoning += reasoning
            self.reasoning_active = True
            if len(self.reasoning) >= 512 or monotonic() - self.last_flush >= 0.1:
                self.flush()
        if text or message.tool_calls or message.response_metadata.get('finish_reason'):
            self.finish_reasoning()
        if text:
            self.text += text
            # Time is checked on arrivals, not with a background timer or SQL session.
            if len(self.text) >= 512 or monotonic() - self.last_flush >= 0.1:
                self.flush()
        if message.usage_metadata is not None:
            with self.session_factory() as db:
                guard_execution(db, self.run_id, self.epoch)
                previous = db.scalar(select(AgentRunEvent).where(
                    AgentRunEvent.run_id == self.run_id, AgentRunEvent.type == 'usage.updated',
                ).order_by(AgentRunEvent.seq.desc()).limit(1).with_for_update())
                total = previous.payload if previous else {'prompt_tokens': 0, 'completion_tokens': 0}
                # Main-model SDK chunks contain additive usage, not a billing total.
                # Retain the observed Run total across recovery;
                # a replayed model request consumes additional tokens and is counted again.
                append_event(db, self.run_id, 'usage.updated', {
                    'prompt_tokens': total['prompt_tokens'] + message.usage_metadata['input_tokens'],
                    'completion_tokens': total['completion_tokens'] + message.usage_metadata['output_tokens'],
                })
                db.commit()

    def finish_reasoning(self):
        if not self.reasoning_active:
            return
        self.flush()
        with self.session_factory() as db:
            guard_execution(db, self.run_id, self.epoch)
            append_event(db, self.run_id, 'assistant.reasoning.done', {})
            db.commit()
        self.reasoning_active = False

    def flush(self):
        if not self.text and not self.reasoning:
            return
        with self.session_factory() as db:
            guard_execution(db, self.run_id, self.epoch)
            if self.reasoning:
                append_event(db, self.run_id, 'assistant.reasoning', {'text': self.reasoning})
            if self.text:
                append_event(db, self.run_id, 'assistant.delta', {'text': self.text})
            db.commit()
        self.text = ''
        self.reasoning = ''
        self.last_flush = monotonic()
