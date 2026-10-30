"""Single-use Redis tickets bind a future socket to the original JWT expiry."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import secrets

from redis.exceptions import RedisError

from backend.infrastructure.redis_client import RedisUnavailable


@dataclass(frozen=True)
class WsTicketClaims:
    user_id: int
    interview_id: str
    auth_expires_at: datetime


class WsTickets:
    def __init__(self, commands, namespace: str):
        self.commands = commands
        self.namespace = namespace

    async def issue_ws_ticket(self, user_id: int, interview_id: str,
                              auth_expires_at: datetime) -> str:
        remaining = (auth_expires_at - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise ValueError('Authentication has expired')
        ticket = secrets.token_urlsafe(32)
        payload = json.dumps({'userId': user_id, 'interviewId': interview_id,
                              'authExpiresAt': auth_expires_at.timestamp()})
        try:
            await self.commands.set(f'{self.namespace}:ws-ticket:{ticket}', payload,
                                    ex=min(30, math.ceil(remaining)))
        except RedisError as exc:
            raise RedisUnavailable('Ticket storage unavailable') from exc
        return ticket

    async def consume_ws_ticket(self, ticket: str) -> WsTicketClaims | None:
        try:
            payload = await self.commands.getdel(f'{self.namespace}:ws-ticket:{ticket}')
        except RedisError as exc:
            raise RedisUnavailable('Ticket storage unavailable') from exc
        if payload is None:
            return None
        value = json.loads(payload)
        expires = datetime.fromtimestamp(value['authExpiresAt'], timezone.utc)
        if datetime.now(timezone.utc) >= expires:
            return None
        return WsTicketClaims(value['userId'], value['interviewId'], expires)
