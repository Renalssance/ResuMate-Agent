from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.db.database import get_db
from backend.db.models import User
from backend.routes.agent_runs import RunRoute
from backend.schemas.memory import MemoryCreate
from backend.services import memory

router = APIRouter(prefix='/api/memories', tags=['memories'], route_class=RunRoute)


@router.get('')
def listing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return memory.list_memories(db, user.id)


@router.post('')
def create(request: MemoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return memory.create_memory(db, user.id, request)


@router.delete('/{memory_id}')
def delete(memory_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return memory.delete_memory(db, user.id, memory_id)
