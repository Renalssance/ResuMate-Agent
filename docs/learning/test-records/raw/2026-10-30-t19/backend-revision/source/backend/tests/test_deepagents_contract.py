"""T01: real SDK + disk checkpoint, deterministic model, no API credentials."""
import json

from deepagents import create_deep_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt


class ApplicationModel(BaseChatModel):
    """Select one business tool, then report its actual returned content."""

    @property
    def _llm_type(self):
        return "resumate-contract-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        answers = [m for m in messages if isinstance(m, ToolMessage)
                   and m.name == "collect_project_role"]
        message = (
            AIMessage(content=answers[-1].content)
            if answers else AIMessage(content="", tool_calls=[{
                "name": "collect_project_role", "args": {}, "id": "role-1",
                "type": "tool_call",
            }])
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


@tool
def collect_project_role() -> str:
    """Ask the applicant to supply their real project role before drafting."""
    answer = interrupt({"kind": "input", "field": "project_role"})
    return json.dumps({"project_role": answer["project_role"]}, ensure_ascii=False)


def build_contract_agent(saver):
    return create_deep_agent(
        model=ApplicationModel(), tools=[collect_project_role], checkpointer=saver,
    )


def test_agent_can_continue_after_user_input_and_checkpoint_reopen(tmp_path):
    checkpoint = str(tmp_path / "checkpoint.sqlite")
    config = {"configurable": {"thread_id": "application-1"}}
    with SqliteSaver.from_conn_string(checkpoint) as saver:
        agent = build_contract_agent(saver)
        paused = agent.invoke({"messages": [{"role": "user", "content": "Prepare my application"}]}, config)
        assert paused["__interrupt__"][0].value == {"kind": "input", "field": "project_role"}
        assert not any(isinstance(m, ToolMessage) for m in paused["messages"])

    # Rebuild BOTH the saver and graph: no in-memory state may supply the answer.
    with SqliteSaver.from_conn_string(checkpoint) as saver:
        agent = build_contract_agent(saver)
        assert agent.get_state(config).next
        finished = agent.invoke(Command(resume={"project_role": "backend"}), config)
        assert not finished.get("__interrupt__")
        assert json.loads(finished["messages"][-1].content) == {"project_role": "backend"}
        assert agent.get_state(config).next == ()
        assert agent.get_state({"configurable": {"thread_id": "another-application"}}).values == {}
