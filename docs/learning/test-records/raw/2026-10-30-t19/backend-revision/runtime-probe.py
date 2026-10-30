"""Run inside the final backend image; real SDK, synthetic in-memory HTTP only."""
import asyncio
import gc
import json
import httpx
from openai import OpenAI, AsyncOpenAI, APIStatusError
from backend.model_transport import DefaultHttpxClient, DefaultAsyncHttpxClient


class Transport(httpx.MockTransport):
    def __init__(self,status):
        self.calls=[]; self.closes=0
        def response(request):
            self.calls.append(request)
            target='https://model.example/sink' if status==307 else 'https://other.example/sink'
            return httpx.Response(status,headers={'location':target})
        super().__init__(response)
    def close(self): self.closes+=1
    async def aclose(self): self.closes+=1


results=[]
for status in (307,308):
 for explicit in (False,True):
    transport=Transport(status)
    client=DefaultHttpxClient(follow_redirects=False,transport=transport)
    sdk=OpenAI(api_key='synthetic-runtime',base_url='https://model.example/v1',timeout=7,max_retries=0,http_client=client)
    try: sdk.chat.completions.create(model='synthetic',messages=[{'role':'user','content':'synthetic'}])
    except APIStatusError: pass
    assert len(transport.calls)==1 and transport.calls[0].url.path!='/sink'
    assert transport.calls[0].extensions['timeout']['read']==7 and sdk.max_retries==0
    if explicit: sdk.close()
    del sdk,client
    gc.collect()
    assert transport.closes==1
    results.append({'mode':'sync','status':status,'explicit_close':explicit,'requests':1,'closes':transport.closes})


async def asynchronous():
 for status in (307,308):
  for explicit in (False,True):
    transport=Transport(status)
    client=DefaultAsyncHttpxClient(follow_redirects=False,transport=transport)
    sdk=AsyncOpenAI(api_key='synthetic-runtime',base_url='https://model.example/v1',timeout=7,max_retries=0,http_client=client)
    try: await sdk.chat.completions.create(model='synthetic',messages=[{'role':'user','content':'synthetic'}])
    except APIStatusError: pass
    assert len(transport.calls)==1 and transport.calls[0].url.path!='/sink'
    assert transport.calls[0].extensions['timeout']['read']==7 and sdk.max_retries==0
    if explicit: await sdk.close()
    del sdk,client
    gc.collect()
    await asyncio.sleep(0)
    assert transport.closes==1
    results.append({'mode':'async','status':status,'explicit_close':explicit,'requests':1,'closes':transport.closes})


asyncio.run(asynchronous())
print(json.dumps({'status':'pass','class_module':DefaultHttpxClient.__module__,'cases':results},indent=2))
