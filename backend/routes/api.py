import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.middleware.rate_limit import require_auth_capacity
from backend.db.database import get_db
from backend.auth.security import authenticate_user, create_access_token, get_current_user, get_password_hash, resolve_role
from backend.db.models import User
from backend.schemas import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
)

# ---- 子路由模块 ----
from backend.routes.chat import router as chat_router
from backend.routes.chat_sessions import router as chat_sessions_router
from backend.routes.runs import router as runs_router
from backend.routes.documents import followup_router, router as documents_router
from backend.routes.tasks import router as tasks_router
from backend.routes.autofill import router as autofill_router
from backend.routes.applications import router as applications_router
from backend.routes.settings import router as settings_router
from backend.routes.agent_runs import router as agent_runs_router
from backend.routes.profile_facts import router as profile_facts_router
from backend.routes.memory import router as memory_router
from backend.routes.interviews import router as interviews_router
from backend.routes.jobs import router as jobs_router
from backend.routes.resume_versions import router as resume_versions_router

router = APIRouter()


@router.get("/api/config")
async def public_config():
    return {"llm_model": os.getenv("LLM_MODEL", "").strip()}

# ==================== 认证 ====================


@router.post("/auth/register", response_model=AuthResponse, dependencies=[Depends(require_auth_capacity)])
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    username = (request.username or "").strip()
    password = (request.password or "").strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")

    role = resolve_role(request.role, request.admin_code)
    user = User(username=username, password_hash=get_password_hash(password), role=role)
    db.add(user)
    db.commit()

    token = create_access_token(username=username, role=role)
    return AuthResponse(access_token=token, username=username, role=role)


@router.post("/auth/login", response_model=AuthResponse, dependencies=[Depends(require_auth_capacity)])
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(username=user.username, role=user.role)
    return AuthResponse(access_token=token, username=user.username, role=user.role)


@router.get("/auth/me", response_model=CurrentUserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return CurrentUserResponse(username=current_user.username, role=current_user.role)


# ==================== 注册子路由 ====================

router.include_router(chat_router)
router.include_router(chat_sessions_router)
router.include_router(runs_router)
router.include_router(documents_router)
router.include_router(followup_router)
router.include_router(tasks_router)
router.include_router(autofill_router)
router.include_router(applications_router)
router.include_router(settings_router)

router.include_router(agent_runs_router)

router.include_router(profile_facts_router)
router.include_router(memory_router)
router.include_router(interviews_router)

router.include_router(jobs_router)

router.include_router(resume_versions_router)
