"""The single Deep Agents construction point; model secrets never enter state."""
from pathlib import Path
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission
from backend.agent_runtime.context import model_budget
from backend.agent_runtime.context_middleware import BusinessContextMiddleware
from deepagents.graph import DeepAgentState
from deepagents.profiles import HarnessProfile, GeneralPurposeSubagentProfile, register_harness_profile
from langchain_openai import ChatOpenAI
from openai import DefaultHttpxClient, DefaultAsyncHttpxClient
from backend.agent_runtime.tools import business_tools
from backend.agent_runtime.telemetry import attach_model_telemetry
from backend.services.llm_settings import resolve_effective_llm_settings
from backend.services.agent_runs import RunError


class RunState(DeepAgentState):
    run_id: str


def model_for_user(user_id: int):
    settings = resolve_effective_llm_settings(user_id)
    if not all((settings.api_key, settings.base_url, settings.model)):
        raise RunError(422, 'model_not_configured', '请先完成个人模型设置')
    if settings.context_window_tokens is None:
        raise RunError(422, 'model_context_not_configured', '请在个人模型设置中填写已核实的上下文容量')
    if int(settings.context_window_tokens * .95) <= settings.max_tokens:
        raise RunError(422, 'context_budget_exceeded', '上下文容量不足以预留输出，请提高容量或降低输出上限')
    return ChatOpenAI(profile={'max_input_tokens': settings.context_window_tokens}, model=settings.model, api_key=settings.api_key, base_url=settings.base_url,
                      max_tokens=settings.max_tokens, timeout=settings.request_timeout_seconds,
                      max_retries=0, stream_usage=True,
                      http_client=DefaultHttpxClient(follow_redirects=False),
                      http_async_client=DefaultAsyncHttpxClient(follow_redirects=False))


def build_agent(user_id: int, checkpointer, *, run_id: str, epoch: int, telemetry=None):
    model = model_for_user(user_id)
    attach_model_telemetry(model, telemetry)
    name = model.model_name
    key = name if name.startswith('openai:') else f'openai:{name}'
    register_harness_profile(key, HarnessProfile(
        excluded_tools=frozenset({'execute', 'task'}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ))
    prompt = (Path(__file__).parent / 'skills/resume-tailoring/SKILL.md').read_text()
    backend = StateBackend()
    budget = model_budget(model)
    input_budget = budget['availableInputEstimatedTokens']
    # Filesystem thresholds assume four characters/token. Convert our one-char
    # planning estimate to keep each paginated read within ~15% of input budget.
    filesystem = FilesystemMiddleware(backend=backend,
        tool_token_limit_before_evict=max(128, int(input_budget * .15 / 4)))
    summarization = BusinessContextMiddleware(model=model, backend=backend, run_id=run_id, epoch=epoch)
    return create_deep_agent(model=model,
        tools=business_tools(run_id, epoch, inline_token_limit=int(input_budget * .1), budget=budget, telemetry=telemetry),
        system_prompt=prompt, state_schema=RunState, backend=backend,
        middleware=[filesystem, summarization],
        permissions=[FilesystemPermission(operations=['write'], paths=['/inputs/**'], mode='deny')],
        checkpointer=checkpointer)


def build_interview_agent(user_id: int, checkpointer, *, run_id: str, epoch: int, telemetry=None):
    from backend.agent_runtime.interview_context import InterviewContextMiddleware, InterviewStep, interview_tools
    model = model_for_user(user_id)
    attach_model_telemetry(model, telemetry)
    name = model.model_name
    register_harness_profile(name if name.startswith('openai:') else f'openai:{name}', HarnessProfile(
        excluded_tools=frozenset({'execute', 'task'}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    backend = StateBackend()
    budget = model_budget(model)
    input_budget = budget['availableInputEstimatedTokens']
    filesystem = FilesystemMiddleware(backend=backend,
        tool_token_limit_before_evict=max(128, int(input_budget * .15 / 4)))
    return create_deep_agent(model=model,
        tools=interview_tools(run_id, epoch, inline_token_limit=int(input_budget * .1), budget=budget),
        system_prompt=(Path(__file__).parent / 'skills/interview-prep/SKILL.md').read_text(),
        response_format=InterviewStep, state_schema=RunState, backend=backend,
        middleware=[filesystem, InterviewContextMiddleware(model=model, backend=backend, run_id=run_id, epoch=epoch)],
        permissions=[FilesystemPermission(operations=['write'], paths=['/inputs/**'], mode='deny')],
        checkpointer=checkpointer)
