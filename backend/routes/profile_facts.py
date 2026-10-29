from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.routes.agent_runs import RunRoute
from backend.schemas.profile_facts import FactCreate, FactUpdate
from backend.services import profile_facts

router = APIRouter(prefix='/api/profile-facts', tags=['profile-facts'], route_class=RunRoute)


@router.post('')
def create(request: FactCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_facts.create_fact(db, user.id, request)


@router.get('')
def listing(source_document_id: int | None = Query(default=None, alias='sourceDocumentId', gt=0),
            include_deleted: bool = Query(default=False, alias='includeDeleted'),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_facts.list_facts(db, user.id, source_document_id=source_document_id, include_deleted=include_deleted)


@router.patch('/{version_id}')
def update(version_id: str, request: FactUpdate,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_facts.update_fact(db, user.id, version_id, request)


@router.delete('/{version_id}')
def delete(version_id: str, expected_revision: int = Query(alias='expectedRevision', ge=1),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_facts.delete_fact(db, user.id, version_id, expected_revision)


@router.get('/{version_id}/history')
def history(version_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_facts.fact_history(db, user.id, version_id)
