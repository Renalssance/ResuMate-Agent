"""Seed only a fresh load project's database; never reset or truncate existing data."""
from datetime import datetime, timedelta
import json
from sqlalchemy import func, select, text
from backend.db.database import SessionLocal
from backend.db.agent_models import AgentRun, AgentRunEvent, AgentSession
from backend.db.models import User, JobDescription

RUN_IDS = [f'load-run-{n:02}' for n in range(10)]

def seed():
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            raise RuntimeError('Load seed requires an empty isolated database')
        db.add(User(id=1, username='load-user', password_hash='not-a-login'))
        db.flush()
        origin = datetime(2026, 1, 1)
        body = '合成岗位：负责接口开发、数据库事务与测试，说明问题并验证结果。' * 24
        for offset in range(0, 10000, 500):
            db.execute(JobDescription.__table__.insert(), [dict(id=n, user_id=1,
                title=f'{"API Engineer" if n % 5 == 0 else "Platform Engineer"} {n}', company=f'Synthetic {n % 100}',
                raw_text=body, structured_data={'requirements': ['SQL', 'API']}, status='archived' if n % 4 == 0 else 'saved',
                captured_at=None if n % 3 == 0 else origin + timedelta(seconds=n),
                created_at=origin + timedelta(seconds=n), updated_at=origin) for n in range(offset + 1, offset + 501)])
        for n, run_id in enumerate(RUN_IDS):
            session_id = f'load-session-{n:02}'
            db.add(AgentSession(id=session_id, user_id=1, purpose='tailoring', active_run_id=run_id))
            db.flush()
            db.add(AgentRun(id=run_id, user_id=1, session_id=session_id, request_id=f'load-seed-{n}',
                kind='tailoring', status='waiting_input', input_json={}, input_versions={}))
            db.flush()
            for offset in range(0, 5000, 500):
                db.execute(AgentRunEvent.__table__.insert(), [dict(run_id=run_id, seq=seq,
                    type='assistant.delta', payload={'text': f'合成历史事件 {seq}'}, created_at=origin)
                    for seq in range(offset + 1, offset + 501)])
        db.commit()
        counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                  for model in (User, JobDescription, AgentRun, AgentRunEvent)}
        explains = {}
        for name, sql in {
            'events': "SELECT * FROM agent_run_events WHERE run_id='load-run-00' AND seq>4900 ORDER BY seq LIMIT 100",
            'jobs_first': 'SELECT * FROM job_descriptions WHERE user_id=1 ORDER BY COALESCE(captured_at,created_at) DESC,id DESC LIMIT 21',
            'jobs_deep': 'SELECT * FROM job_descriptions WHERE user_id=1 ORDER BY COALESCE(captured_at,created_at) DESC,id DESC LIMIT 21 OFFSET 8000',
            'jobs_search': "SELECT * FROM job_descriptions WHERE user_id=1 AND (title LIKE '%API%' OR company LIKE '%API%') ORDER BY COALESCE(captured_at,created_at) DESC,id DESC LIMIT 21",
        }.items():
            explains[name] = [dict(row) for row in db.execute(text('EXPLAIN ' + sql)).mappings()]
        return {'counts': counts, 'run_ids': RUN_IDS, 'initial_seq': 5000,
                'job_text_bytes': len(body.encode()), 'explains': explains,
                'mysql': db.scalar(text('SELECT VERSION()'))}

if __name__ == '__main__':
    print(json.dumps(seed(), ensure_ascii=False, default=str))
