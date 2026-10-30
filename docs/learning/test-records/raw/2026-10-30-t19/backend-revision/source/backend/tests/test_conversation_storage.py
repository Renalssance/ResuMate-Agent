from langchain_core.messages import HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.agent.agent import ConversationStorage
from backend.db.database import Base
from backend.db.models import User


def test_conversation_storage_round_trips_without_cache(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        db.add(User(username="alice", password_hash="hash", role="user"))
        db.commit()
    storage = ConversationStorage(session_factory=sessions)
    storage.save("alice", "session-1", [HumanMessage(content="hello")])
    assert [message.content for message in storage.load("alice", "session-1")] == ["hello"]
