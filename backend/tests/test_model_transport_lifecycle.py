"""Explicit model transports retain SDK cleanup in real chat completion/cancellation."""
import asyncio
import gc
import json
from types import SimpleNamespace
import weakref

import httpx
import pytest
from backend.agent import agent


def sse(delta, reason=None):
    value={'id':'synthetic-stream','object':'chat.completion.chunk','created':1,'model':'synthetic',
           'choices':[{'index':0,'delta':delta,'finish_reason':reason}]}
    return ('data: '+json.dumps(value)+'\n\n').encode()


class Stream(httpx.AsyncByteStream):
    def __init__(self, hold):
        self.hold=hold
        self.closed=False
    async def __aiter__(self):
        yield sse({'role':'assistant','content':'synthetic answer'})
        if self.hold:
            await asyncio.Event().wait()
        yield sse({},'stop')
        yield b'data: [DONE]\n\n'
    async def aclose(self):
        self.closed=True


class SyncTransport(httpx.BaseTransport):
    def __init__(self): self.closes=0
    def close(self): self.closes+=1


class AsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, hold): self.closes=0; self.calls=0; self.stream=Stream(hold)
    async def handle_async_request(self, request):
        self.calls+=1
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=self.stream)
    async def aclose(self): self.closes+=1


@pytest.mark.parametrize('disconnect',[False,True],ids=['normal-completion','browser-disconnect'])
def test_production_chat_releases_owned_transport(monkeypatch,disconnect):
    DefaultHttpxClient = agent.DefaultHttpxClient
    DefaultAsyncHttpxClient = agent.DefaultAsyncHttpxClient
    settings=SimpleNamespace(model='synthetic',api_key='synthetic-key',base_url='https://synthetic.example/v1',request_timeout_seconds=7)
    class DB:
        def query(self,*args): return self
        def filter(self,*args): return self
        def first(self): return SimpleNamespace(id=1)
        def close(self): pass
    sync=SyncTransport(); asynchronous=AsyncTransport(disconnect); refs=[]
    def make_sync(**kwargs):
        client=DefaultHttpxClient(transport=sync,**kwargs); refs.append(weakref.ref(client)); return client
    def make_async(**kwargs):
        client=DefaultAsyncHttpxClient(transport=asynchronous,**kwargs); refs.append(weakref.ref(client)); return client
    monkeypatch.setattr(agent,'SessionLocal',DB)
    monkeypatch.setattr(agent,'resolve_effective_llm_settings',lambda *_:settings)
    monkeypatch.setattr(agent,'create_interview_tools',lambda *_:[])
    monkeypatch.setattr(agent,'DefaultHttpxClient',make_sync)
    monkeypatch.setattr(agent,'DefaultAsyncHttpxClient',make_async)
    monkeypatch.setattr(agent,'storage',SimpleNamespace(load=lambda *_:[],save=lambda *_:None))
    monkeypatch.setattr(agent,'record_llm_usage',lambda **_:None)
    async def exercise():
        stream=agent.chat_with_agent_stream('synthetic question','synthetic-user','synthetic-session')
        chunks=[]
        async for chunk in stream:
            chunks.append(chunk)
            if disconnect and 'synthetic answer' in chunk:
                await stream.aclose()
                break
        del stream
        await asyncio.sleep(0.01)  # Let completed graph-task callbacks leave the event loop.
        gc.collect()
        await asyncio.sleep(0)
        assert asynchronous.calls==1
        assert asynchronous.stream.closed, 'SDK response body must finish/cancel before pool cleanup'
        if not disconnect:
            assert any('[DONE]' in chunk for chunk in chunks)
        assert not any(ref() is not None for ref in refs), 'Do not retain client objects in the test'
        assert (sync.closes,asynchronous.closes)==(1,1), 'Production-owned transports were never closed'
    asyncio.run(exercise())


@pytest.mark.parametrize('explicit_close',[False,True],ids=['garbage-collected','already-closed'])
def test_sync_client_cleanup_is_idempotent(explicit_close):
    transport=SyncTransport()
    client=agent.DefaultHttpxClient(transport=transport,follow_redirects=False)
    assert client.follow_redirects is False
    ref=weakref.ref(client)
    if explicit_close: client.close()
    del client
    gc.collect()
    assert ref() is None
    assert transport.closes == 1


@pytest.mark.parametrize('explicit_close',[False,True],ids=['garbage-collected','already-closed'])
def test_async_client_cleanup_is_idempotent(explicit_close):
    async def exercise():
        transport=AsyncTransport(False)
        client=agent.DefaultAsyncHttpxClient(transport=transport,follow_redirects=False)
        assert client.follow_redirects is False
        ref=weakref.ref(client)
        if explicit_close: await client.aclose()
        del client
        gc.collect()
        await asyncio.sleep(0)
        assert ref() is None
        assert transport.closes == 1
    asyncio.run(exercise())
