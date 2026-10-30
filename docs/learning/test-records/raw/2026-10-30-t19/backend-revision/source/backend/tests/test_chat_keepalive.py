import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessageChunk

from backend.agent import agent


def test_chat_sends_headers_and_heartbeats_while_model_is_silent(monkeypatch):
    saved = []

    class SilentThenReply:
        async def astream(self, *args, **kwargs):
            await asyncio.sleep(0)
            yield AIMessageChunk(content="hello"), {}

    monkeypatch.setattr(agent, "storage", SimpleNamespace(load=lambda *_: [], save=lambda *args: saved.append(args)))
    monkeypatch.setattr(agent, "create_agent_with_interview_tools", lambda *_: (SilentThenReply(), None, 1, SimpleNamespace(model="own-model", base_url="https://own.example/v1")))
    monkeypatch.setattr(agent, "record_llm_usage", lambda **_: None)
    original_wait = asyncio.wait_for
    waits = []

    async def wait_with_one_idle_interval(awaitable, timeout):
        waits.append(timeout)
        if len(waits) == 1:
            awaitable.close()
            raise TimeoutError
        return await original_wait(awaitable, timeout)

    monkeypatch.setattr(agent.asyncio, "wait_for", wait_with_one_idle_interval)

    async def collect():
        return [chunk async for chunk in agent.chat_with_agent_stream("hi", "user", "session")]

    chunks = asyncio.run(collect())
    assert chunks[:2] == [": heartbeat\n\n", ": heartbeat\n\n"]
    assert '"content": "hello"' in chunks[2]
    assert chunks[-1] == "data: [DONE]\n\n"
    assert waits[0] == 15
    assert saved
