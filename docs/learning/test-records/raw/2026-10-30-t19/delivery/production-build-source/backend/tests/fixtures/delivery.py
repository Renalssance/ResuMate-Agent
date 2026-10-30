"""T19 deterministic model and synthetic data; never a production switch."""
import json
from pathlib import Path
import sys
from sqlalchemy import select
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.agent_runtime import factory
from backend.db.database import SessionLocal
from backend.db.models import User, Resume, JobDescription
from backend.db.agent_models import AgentRun, AgentAction, ToolOperation, AgentRunEvent
from backend.db.career_models import ResumeVersion
from backend.tests.agent_fixtures import DraftModel
from backend.tests.resume_pdf_fixture import chinese_resume_content
from backend.worker import app  # noqa: F401

factory.model_for_user = lambda _: DraftModel(ask=True)


def seed():
    original = Path('/app/data/documents/delivery-original.txt')
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_text('Synthetic original resume: API development')
    with SessionLocal() as db:
        db.add(User(id=1, username='delivery-user', password_hash='not-a-login'))
        db.flush()
        db.add_all([Resume(id=1, user_id=1, filename=original.name, file_path=str(original),
            raw_text=original.read_text(), structured_data={'self_summary': 'API development'}),
            JobDescription(id=1, user_id=1, title='Engineer', raw_text='Build APIs')])
        db.flush()
        db.add(ResumeVersion(id='delivery-confirmed', user_id=1, resume_id=1, jd_id=1,
            status='confirmed', revision=3, structured_content=chinese_resume_content()))
        db.commit()
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(path='/app/data/chroma', settings=Settings(anonymized_telemetry=False))
    client.get_or_create_collection('delivery-probe').add(ids=['original'], documents=['API development'], embeddings=[[1.0, 0.0, 0.0]])
    return {'seeded': True}


def inspect(run_id):
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        result = {'run_id': run.id, 'session_id': run.session_id, 'status': run.status,
            'versions': db.query(ResumeVersion).filter_by(run_id=run_id).count(),
            'operations': db.query(ToolOperation).filter_by(run_id=run_id).count(),
            'actions': [{'id': a.id, 'status': a.status, 'response': a.response}
                        for a in db.scalars(select(AgentAction).where(AgentAction.run_id == run_id))],
            'events': [{'seq': e.seq, 'type': e.type, 'payload': e.payload}
                       for e in db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).order_by(AgentRunEvent.seq))]}
        sid, uid, epoch = run.session_id, run.user_id, run.execution_epoch
    with SqliteSaver.from_conn_string('/app/agent-state/checkpoints.sqlite') as saver:
        graph = factory.build_agent(uid, saver, run_id=run_id, epoch=epoch)
        state = graph.get_state({'configurable': {'thread_id': sid}})
        result['checkpoint'] = {'run_id': state.values.get('run_id'), 'next': list(state.next),
            'interrupts': [i.id for i in state.interrupts], 'message_count': len(state.values.get('messages', []))}
    return result


def files():
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(path='/app/data/chroma', settings=Settings(anonymized_telemetry=False))
    return {'original': Path('/app/data/documents/delivery-original.txt').read_text(),
        'chroma': client.get_collection('delivery-probe').get()['documents'],
        'pdf_count': len(list(Path('/app/data/exports').glob('*.pdf')))}


if __name__ == '__main__':
    print(json.dumps({'seed': seed, 'inspect': lambda: inspect(sys.argv[2]), 'files': files}[sys.argv[1]](), ensure_ascii=False))
