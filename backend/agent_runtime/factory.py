"""The single Deep Agents construction point; model secrets never enter state."""
from pathlib import Path
from deepagents import create_deep_agent
from deepagents.graph import DeepAgentState
from deepagents.profiles import HarnessProfile, GeneralPurposeSubagentProfile, register_harness_profile
from langchain_openai import ChatOpenAI
from backend.agent_runtime.tools import business_tools
from backend.services.llm_settings import resolve_effective_llm_settings
from backend.services.agent_runs import RunError


class RunState(DeepAgentState):
    run_id: str


def model_for_user(user_id: int):
    settings = resolve_effective_llm_settings(user_id)
    if not all((settings.api_key, settings.base_url, settings.model)):
        raise RunError(422, 'model_not_configured', '请先完成个人模型设置')
    return ChatOpenAI(model=settings.model, api_key=settings.api_key, base_url=settings.base_url,
                      max_tokens=settings.max_tokens, timeout=settings.request_timeout_seconds,
                      max_retries=0, stream_usage=True)


def build_agent(user_id: int, checkpointer, *, run_id: str, epoch: int):
    model = model_for_user(user_id)
    name = model.model_name
    key = name if name.startswith('openai:') else f'openai:{name}'
    register_harness_profile(key, HarnessProfile(
        excluded_tools=frozenset({'execute', 'task'}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ))
    prompt = (Path(__file__).parent / 'skills/resume-tailoring/SKILL.md').read_text()
    # Default StateBackend is checkpoint-scoped memory, not the host filesystem.
    return create_deep_agent(model=model, tools=business_tools(run_id, epoch),
                             system_prompt=prompt, state_schema=RunState,
                             checkpointer=checkpointer)
