"""Short SQL reads for the durable event stream; Redis hints carry no event body."""
from fastapi import HTTPException

from backend.db.career_models import InterviewEvent, InterviewSession


def read_interview_events(session_factory, user_id: int, interview_id: str,
                          after_seq: int, limit: int = 100) -> list[dict]:
    with session_factory() as db:
        owned = (db.query(InterviewSession).filter(InterviewSession.id == interview_id,
                                                  InterviewSession.user_id == user_id).first())
        if owned is None:
            raise HTTPException(status_code=404, detail='面试会话不存在')
        rows = (db.query(InterviewEvent).filter(InterviewEvent.interview_id == interview_id,
                                               InterviewEvent.seq > after_seq)
                .order_by(InterviewEvent.seq).limit(limit).all())
        return [{'interviewId': interview_id, 'seq': row.seq, 'type': row.type,
                 'payload': row.payload} for row in rows]
