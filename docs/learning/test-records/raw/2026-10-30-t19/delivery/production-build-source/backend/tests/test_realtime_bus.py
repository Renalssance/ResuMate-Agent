"""Hints wake local readers without carrying business data or replacing SQL."""
import asyncio
import json

import pytest
from redis.exceptions import ConnectionError


class PubSub:
    def __init__(self, messages):
        self.messages = messages
        self.channels = []
        self.closed = False
        self.subscribed = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def subscribe(self, channel):
        self.channels.append(channel)
        self.subscribed.set()

    async def get_message(self, **kwargs):
        item = await self.messages.get()
        if isinstance(item, Exception):
            raise item
        return {'data': item}


class Notifications:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.subscriptions = []

    def pubsub(self):
        subscription = PubSub(self.messages)
        self.subscriptions.append(subscription)
        return subscription


class Commands:
    def __init__(self):
        self.published = []
        self.failure = False

    async def publish(self, channel, value):
        if self.failure:
            raise ConnectionError('unavailable')
        self.published.append((channel, json.loads(value)))


@pytest.mark.asyncio
async def test_hints_wake_only_registered_interview_and_close_reader():
    from backend.services.realtime_bus import InterviewHints
    commands, notifications = Commands(), Notifications()
    hints = InterviewHints(commands, notifications, 'resumate:test')
    await hints.start()
    await asyncio.sleep(0)
    await notifications.subscriptions[0].subscribed.wait()
    async with hints.watch('owned') as event, hints.watch('other') as other:
        await notifications.messages.put(json.dumps({'interviewId':'owned', 'lastSeq':2}))
        await asyncio.wait_for(event.wait(), .5)
        assert not other.is_set()
        assert notifications.subscriptions[0].channels == ['resumate:test:interview-hints']
        await hints.publish_interview_hint('owned', 2)
        assert commands.published == [('resumate:test:interview-hints', {'interviewId':'owned', 'lastSeq':2})]
    event.clear()
    await notifications.messages.put(json.dumps({'interviewId':'owned', 'lastSeq':3}))
    await asyncio.sleep(.01)
    assert not event.is_set()
    await hints.aclose()
    assert notifications.subscriptions[0].closed


@pytest.mark.asyncio
async def test_disconnected_reader_resubscribes_and_commands_fail_explicitly():
    from backend.services.realtime_bus import InterviewHints
    from backend.infrastructure.redis_client import RedisUnavailable
    commands, notifications = Commands(), Notifications()
    hints = InterviewHints(commands, notifications, 'resumate:test')
    await hints.start()
    await asyncio.sleep(0)
    await notifications.subscriptions[0].subscribed.wait()
    await notifications.messages.put(ConnectionError('lost connection'))
    async with hints.watch('owned') as event:
        await notifications.messages.put(json.dumps({'interviewId':'owned', 'lastSeq':3}))
        await asyncio.wait_for(event.wait(), 2)
    assert notifications.subscriptions[0].closed
    assert len(notifications.subscriptions) == 2
    commands.failure = True
    with pytest.raises(RedisUnavailable):
        await hints.publish_interview_hint('owned', 4)
    await hints.aclose()
    assert all(subscription.closed for subscription in notifications.subscriptions)


def test_worker_hint_uses_process_client_and_minimal_payload(monkeypatch):
    from backend.services import realtime_bus
    from backend.infrastructure.redis_client import RedisUnavailable
    class SyncCommands:
        def __init__(self):
            self.published = []
        def publish(self, channel, value):
            self.published.append((channel, json.loads(value)))
    commands = SyncCommands()
    monkeypatch.setattr(realtime_bus, 'get_sync_redis', lambda: commands)
    monkeypatch.setattr(realtime_bus, 'redis_namespace', lambda: 'resumate:worker')
    realtime_bus.publish_interview_hint_sync('owned', 5)
    assert commands.published == [('resumate:worker:interview-hints', {'interviewId':'owned', 'lastSeq':5})]
    def fail(*args):
        raise ConnectionError('unavailable')
    monkeypatch.setattr(commands, 'publish', fail)
    with pytest.raises(RedisUnavailable):
        realtime_bus.publish_interview_hint_sync('owned', 6)
