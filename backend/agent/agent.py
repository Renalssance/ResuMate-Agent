import asyncio
import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from backend.agent.interview_tools import create_interview_tools
from backend.db.cache import cache
from backend.db.database import SessionLocal
from backend.db.models import ChatMessage, ChatSession, User
from backend.logging_config import log_llm_prompt, log_llm_response

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("ARK_API_KEY")
MODEL = os.getenv("MODEL")
BASE_URL = os.getenv("BASE_URL")

MAX_CONTEXT_MESSAGES = 20


class ConversationStorage:
    """Minimal conversation storage for the interview assistant chat surface."""

    @staticmethod
    def _messages_cache_key(user_id: str, session_id: str) -> str:
        return f"chat_messages:{user_id}:{session_id}"

    @staticmethod
    def _to_langchain_messages(records: list[dict]) -> list:
        messages = []
        for msg_data in records:
            content = msg_data.get("content", "")
            if msg_data.get("type") == "human":
                messages.append(HumanMessage(content=content))
            elif msg_data.get("type") == "ai":
                messages.append(AIMessage(content=content))
        return messages

    def save(self, user_id: str, session_id: str, messages: list):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return

            session = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id, ChatSession.session_id == session_id)
                .first()
            )
            if not session:
                session = ChatSession(user_id=user.id, session_id=session_id, metadata_json={})
                db.add(session)
                db.flush()

            db.query(ChatMessage).filter(ChatMessage.session_ref_id == session.id).delete(synchronize_session=False)

            serialized = []
            now = datetime.utcnow()
            for msg in messages[-MAX_CONTEXT_MESSAGES:]:
                db.add(
                    ChatMessage(
                        session_ref_id=session.id,
                        message_type=msg.type,
                        content=str(msg.content),
                        timestamp=now,
                    )
                )
                serialized.append(
                    {
                        "type": msg.type,
                        "content": str(msg.content),
                        "timestamp": now.isoformat(),
                    }
                )

            session.updated_at = now
            db.commit()
            cache.set_json(self._messages_cache_key(user_id, session_id), serialized)
        finally:
            db.close()

    def load(self, user_id: str, session_id: str) -> list:
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            return self._to_langchain_messages(cached[-MAX_CONTEXT_MESSAGES:])

        records = self.get_session_messages(user_id, session_id)
        cache.set_json(self._messages_cache_key(user_id, session_id), records)
        return self._to_langchain_messages(records[-MAX_CONTEXT_MESSAGES:])

    def get_session_messages(self, user_id: str, session_id: str) -> list[dict]:
        cached = cache.get_json(self._messages_cache_key(user_id, session_id))
        if cached is not None:
            return cached

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == user_id).first()
            if not user:
                return []
            session = (
                db.query(ChatSession)
                .filter(ChatSession.user_id == user.id, ChatSession.session_id == session_id)
                .first()
            )
            if not session:
                return []

            rows = (
                db.query(ChatMessage)
                .filter(ChatMessage.session_ref_id == session.id)
                .order_by(ChatMessage.id.asc())
                .all()
            )
            result = [
                {
                    "type": row.message_type,
                    "content": row.content,
                    "timestamp": row.timestamp.isoformat(),
                }
                for row in rows
            ]
            cache.set_json(self._messages_cache_key(user_id, session_id), result)
            return result
        finally:
            db.close()

def _build_system_prompt() -> str:
    return (
        "You are a professional interview coach and recruiting assistant. "
        "Focus only on resume parsing, JD analysis, resume-JD matching, interview question generation, "
        "and mock interview evaluation.\n\n"
        "Use the available tools when the user asks to analyze a resume, analyze a JD, match a resume "
        "with a JD, generate interview questions, or evaluate an interview answer. "
        "Do not claim to have knowledge-base, weather, or long-term memory capabilities."
    )


def create_agent_with_interview_tools(user_id: str):
    logger.info("Creating interview agent | user_id=%s model=%s base_url=%s", user_id, MODEL, BASE_URL)
    model = init_chat_model(
        model=MODEL,
        model_provider="openai",
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0.3,
        stream_usage=True,
    )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == user_id).first()
        int_user_id = user.id if user else 0
    finally:
        db.close()

    system_prompt = _build_system_prompt()
    agent = create_agent(
        model=model,
        tools=create_interview_tools(int_user_id),
        system_prompt=system_prompt,
    )
    logger.info("Interview agent created | user_id=%s int_user_id=%s", user_id, int_user_id)
    return agent, model


storage = ConversationStorage()


async def chat_with_agent_stream(user_text: str, user_id: str = "default_user", session_id: str = "default_session"):
    messages = storage.load(user_id, session_id)
    messages.append(HumanMessage(content=user_text))
    logger.info(
        "Chat stream start | user_id=%s session_id=%s history_messages=%s user_text_chars=%s",
        user_id,
        session_id,
        len(messages) - 1,
        len(user_text),
    )
    prompt_snapshot = {
        "system_prompt": _build_system_prompt(),
        "messages": [{"type": msg.type, "content": str(msg.content)} for msg in messages],
    }
    log_llm_prompt(
        "agent.chat_stream",
        json.dumps(prompt_snapshot, ensure_ascii=False, indent=2),
        {"user_id": user_id, "session_id": session_id, "message_count": len(messages)},
    )

    output_queue = asyncio.Queue()
    full_response = ""
    agent, _ = create_agent_with_interview_tools(user_id)

    async def _agent_worker():
        nonlocal full_response
        try:
            async for msg, _ in agent.astream(
                {"messages": messages},
                stream_mode="messages",
                config={"recursion_limit": 12},
            ):
                if not isinstance(msg, AIMessageChunk):
                    continue
                if getattr(msg, "tool_call_chunks", None):
                    continue

                content = ""
                if isinstance(msg.content, str):
                    content = msg.content
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, str):
                            content += block
                        elif isinstance(block, dict) and block.get("type") == "text":
                            content += block.get("text", "")

                if content:
                    full_response += content
                    await output_queue.put({"type": "content", "content": content})
        except Exception as exc:
            logger.exception("Agent stream failed")
            await output_queue.put({"type": "error", "content": str(exc)})
        finally:
            await output_queue.put(None)

    agent_task = asyncio.create_task(_agent_worker())

    try:
        while True:
            event = await output_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except GeneratorExit:
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        raise
    finally:
        if not agent_task.done():
            agent_task.cancel()

    yield "data: [DONE]\n\n"

    logger.info(
        "Chat stream completed | user_id=%s session_id=%s response_chars=%s",
        user_id,
        session_id,
        len(full_response),
    )
    log_llm_response(
        "agent.chat_stream",
        full_response,
        {"user_id": user_id, "session_id": session_id, "response_chars": len(full_response)},
    )
    messages.append(AIMessage(content=full_response))
    storage.save(user_id, session_id, messages)
