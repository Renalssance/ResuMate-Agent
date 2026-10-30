"""Contracts before T16 business commands and T21 WebSockets exist."""
import asyncio
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError
from sqlalchemy.orm import sessionmaker

from backend.auth import security
from backend.db.career_models import InterviewEvent, InterviewSession, ResumeVersion
from backend.tests.career_fixtures import career_db, career_engine


class TicketStore:
    def __init__(self):
        self.rows = {}
        self.expiries = {}
        self.failure = False

    async def set(self, key, value, *, ex):
        if self.failure:
            raise ConnectionError('test unavailable')
        self.rows[key] = value
        self.expiries[key] = ex

    async def getdel(self, key):
        if self.failure:
            raise ConnectionError('test unavailable')
        return self.rows.pop(key, None)


@pytest.mark.asyncio
async def test_ticket_is_consumed_once_and_bound_to_original_expiration():
    from backend.services.ws_tickets import WsTickets
    store = TicketStore()
    tickets = WsTickets(store, 'resumate:test')
    expiry = datetime.now(timezone.utc) + timedelta(seconds=18)
    token = await tickets.issue_ws_ticket(7, 'interview-id', expiry)
    key = 'resumate:test:ws-ticket:' + token
    assert 0 < store.expiries[key] <= 18
    assert json.loads(store.rows[key])['authExpiresAt'] == expiry.timestamp()
    claims = await tickets.consume_ws_ticket(token)
    assert claims.user_id == 7 and claims.interview_id == 'interview-id'
    assert claims.auth_expires_at == expiry
    assert await tickets.consume_ws_ticket(token) is None


@pytest.mark.asyncio
async def test_ticket_never_extends_expired_auth_or_hides_redis_failure():
    from backend.services.ws_tickets import WsTickets
    from backend.infrastructure.redis_client import RedisUnavailable
    store = TicketStore()
    tickets = WsTickets(store, 'resumate:test')
    with pytest.raises(ValueError):
        await tickets.issue_ws_ticket(1, 'owned', datetime.now(timezone.utc)-timedelta(seconds=1))
    token = await tickets.issue_ws_ticket(1, 'owned', datetime.now(timezone.utc)+timedelta(seconds=120))
    assert store.expiries['resumate:test:ws-ticket:'+token] == 30
    payload = json.loads(store.rows['resumate:test:ws-ticket:'+token])
    payload['authExpiresAt'] = datetime.now(timezone.utc).timestamp()-1
    store.rows['resumate:test:ws-ticket:'+token] = json.dumps(payload)
    assert await tickets.consume_ws_ticket(token) is None
    store.failure = True
    with pytest.raises(RedisUnavailable):
        await tickets.consume_ws_ticket('unknown')
    with pytest.raises(RedisUnavailable):
        await tickets.issue_ws_ticket(1, 'owned', datetime.now(timezone.utc)+timedelta(seconds=60))


def test_auth_context_uses_signed_exp_and_sql_identity(career_db):
    token = security.create_access_token('alice', 'invented-admin')
    context = security.get_current_auth(token, career_db)
    assert context.user.id == 1 and context.user.role != 'invented-admin'
    assert context.auth_expires_at > datetime.now(timezone.utc)
    assert security.get_current_user(token, career_db).id == 1
    no_exp = security.jwt.encode({'sub':'alice'}, security.SECRET_KEY, algorithm=security.ALGORITHM)
    with pytest.raises(HTTPException) as error:
        security.get_current_auth(no_exp, career_db)
    assert error.value.status_code == 401


def test_interview_event_pages_are_owned_ordered_and_fresh(career_db):
    from backend.services.interview_events import read_interview_events
    career_db.add(ResumeVersion(id='version', user_id=1, status='confirmed',
                                structured_content={'resume': {}}))
    career_db.flush()
    career_db.add(InterviewSession(id='interview', user_id=1, resume_version_id='version'))
    career_db.flush()
    career_db.add(InterviewEvent(interview_id='interview', seq=1, type='started', payload={}))
    career_db.commit()
    factory = sessionmaker(bind=career_db.get_bind())
    assert read_interview_events(factory, 1, 'interview', 0) == [
        {'interviewId':'interview', 'seq':1, 'type':'started', 'payload':{}}]
    career_db.add(InterviewEvent(interview_id='interview', seq=2, type='question.ready', payload={'text':'Synthetic question'}))
    career_db.commit()
    assert [row['seq'] for row in read_interview_events(factory, 1, 'interview', 1)] == [2]
    assert [row['seq'] for row in read_interview_events(factory, 1, 'interview', 0, limit=1)] == [1]
    with pytest.raises(HTTPException) as error:
        read_interview_events(factory, 2, 'interview', 0)
    assert error.value.status_code == 404
