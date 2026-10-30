"""Real SQL seeds shared by interview service/runtime tests."""
from datetime import date
from uuid import uuid4

from backend.db.agent_models import AgentRun
from backend.db.career_models import InterviewTurn, ResumeVersion
from backend.db.models import JobApplication
from backend.schemas.resume_versions import VersionStatus
from backend.services.applications import attach_submission


def seed_application(db, *, user_id=1, application_id=1):
    version = ResumeVersion(id=str(uuid4()), user_id=user_id, resume_id=1, jd_id=1,
        status=VersionStatus.CONFIRMED, revision=3,
        structured_content={'resume': {'self_summary': 'Built an API',
            'work_experience': [{'description': 'Designed SQL transactions'}]}, 'changes': []},
        fact_refs=[])
    db.add(version)
    db.flush()
    db.add(JobApplication(id=application_id, user_id=user_id, company='Example',
                          position='Engineer', applied_date=date(2026, 10, 30)))
    db.flush()
    attach_submission(db, user_id, application_id, 1, version.id)
    db.commit()
    return db.get(JobApplication, application_id)


def seed_question(db, created, *, question='How did you build the API?', turn=1):
    from backend.services import agent_runs, interviews
    from backend.schemas.agent_runs import RunStatus
    epoch = agent_runs.claim_run(db, created['runId'])
    run, interview, _ = interviews.guard_interview_execution(db, created['runId'], epoch)
    row = InterviewTurn(interview_id=interview.id, turn_index=turn, question=question,
                        question_context={'mode': 'opening', 'refs': []})
    db.add(row)
    interviews.append_interview_event(db, interview.id, 'question.completed', {'turnIndex': turn})
    interviews.finish_interview_generation(db, run.id, epoch, RunStatus.SUCCEEDED, result_json={'seed': True})
    return row


def answer_command(message_id='message-1', *, turn=1, text='I used one SQL transaction'):
    from backend.schemas.interviews import INTERVIEW_COMMAND_ADAPTER
    return INTERVIEW_COMMAND_ADAPTER.validate_python({'clientMessageId': message_id,
        'type': 'answer.submit', 'expectedTurn': turn, 'payload': {'text': text}})
