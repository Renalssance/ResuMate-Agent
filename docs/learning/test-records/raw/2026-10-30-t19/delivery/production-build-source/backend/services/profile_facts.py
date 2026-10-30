"""Append-only user facts. Select newest versions before applying visibility filters."""
from datetime import timezone
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.career_models import ProfileFact
from backend.db.models import Resume, utcnow
from backend.schemas.profile_facts import FactCreate, FactUpdate
from backend.services.agent_runs import RunError


def serialize(fact: ProfileFact) -> dict:
    return {
        'id': fact.id, 'factKey': fact.fact_key, 'kind': fact.kind, 'content': fact.content,
        'sourceDocumentId': fact.source_document_id, 'revision': fact.revision,
        'confirmedAt': fact.confirmed_at.replace(tzinfo=timezone.utc).isoformat() if fact.confirmed_at else None,
        'deletedAt': fact.deleted_at.replace(tzinfo=timezone.utc).isoformat() if fact.deleted_at else None,
    }


def require_resume(db: Session, user_id: int, document_id: int | None) -> None:
    if document_id is not None and db.scalar(select(Resume.id).where(
            Resume.id == document_id, Resume.user_id == user_id)) is None:
        raise RunError(404, 'not_found', '来源简历不存在')


def latest_statement(user_id: int):
    latest = select(ProfileFact.fact_key, func.max(ProfileFact.revision).label('revision')).where(
        ProfileFact.user_id == user_id).group_by(ProfileFact.fact_key).subquery()
    return select(ProfileFact).join(latest, and_(
        ProfileFact.fact_key == latest.c.fact_key, ProfileFact.revision == latest.c.revision,
    )).where(ProfileFact.user_id == user_id)


def latest_facts(db: Session, user_id: int, *, source_document_id: int | None = None,
                 include_deleted=False, confirmed_only=False) -> list[ProfileFact]:
    statement = latest_statement(user_id)
    if source_document_id is not None:
        statement = statement.where(or_(ProfileFact.source_document_id.is_(None),
                                        ProfileFact.source_document_id == source_document_id))
    if not include_deleted:
        statement = statement.where(ProfileFact.deleted_at.is_(None))
    if confirmed_only:
        statement = statement.where(ProfileFact.confirmed_at.is_not(None))
    return list(db.scalars(statement.order_by(ProfileFact.fact_key)))


def list_facts(db: Session, user_id: int, *, source_document_id=None, include_deleted=False) -> dict:
    require_resume(db, user_id, source_document_id)
    return {'items': [serialize(fact) for fact in latest_facts(
        db, user_id, source_document_id=source_document_id, include_deleted=include_deleted)]}


def create_fact(db: Session, user_id: int, request: FactCreate) -> dict:
    require_resume(db, user_id, request.source_document_id)
    fact = ProfileFact(id=str(uuid4()), fact_key=str(uuid4()), user_id=user_id,
                       kind=request.kind, content=request.content, source_document_id=request.source_document_id,
                       revision=1, confirmed_at=utcnow() if request.confirmed else None)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return serialize(fact)


def get_fact(db: Session, user_id: int, version_id: str) -> ProfileFact:
    fact = db.scalar(select(ProfileFact).where(ProfileFact.id == version_id, ProfileFact.user_id == user_id))
    if fact is None:
        raise RunError(404, 'not_found', '事实不存在')
    return fact


def _append(db: Session, user_id: int, version_id: str, expected_revision: int,
            *, request: FactUpdate | None = None) -> dict:
    old = get_fact(db, user_id, version_id)
    latest = db.scalar(select(func.max(ProfileFact.revision)).where(
        ProfileFact.user_id == user_id, ProfileFact.fact_key == old.fact_key))
    if old.revision != expected_revision or latest != old.revision or old.deleted_at:
        raise RunError(409, 'fact_conflict', '事实版本已变化，请查看最新版本后重试')
    fact = ProfileFact(id=str(uuid4()), user_id=user_id, fact_key=old.fact_key,
                       kind=old.kind, source_document_id=old.source_document_id, revision=old.revision + 1,
                       content=request.content if request else old.content,
                       confirmed_at=utcnow() if request and request.confirmed else None,
                       deleted_at=utcnow() if request is None else None)
    db.add(fact)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise RunError(409, 'fact_conflict', '事实版本已变化，请查看最新版本后重试') from error
    db.refresh(fact)
    return serialize(fact)


def update_fact(db: Session, user_id: int, version_id: str, request: FactUpdate) -> dict:
    return _append(db, user_id, version_id, request.expected_revision, request=request)


def delete_fact(db: Session, user_id: int, version_id: str, expected_revision: int) -> dict:
    return _append(db, user_id, version_id, expected_revision)


def fact_history(db: Session, user_id: int, version_id: str) -> dict:
    fact = get_fact(db, user_id, version_id)
    rows = db.scalars(select(ProfileFact).where(
        ProfileFact.user_id == user_id, ProfileFact.fact_key == fact.fact_key).order_by(ProfileFact.revision))
    return {'items': [serialize(row) for row in rows]}
