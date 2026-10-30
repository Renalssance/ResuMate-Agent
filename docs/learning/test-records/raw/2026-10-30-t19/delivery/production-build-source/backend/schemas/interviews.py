"""One typed interview command contract for HTTP and WebSocket callers."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter


class InterviewPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True, str_strip_whitespace=True)


class InterviewCreate(InterviewPayload):
    request_id: str = Field(alias='requestId', min_length=1, max_length=100)
    application_id: int = Field(alias='applicationId', gt=0)


class AnswerPayload(InterviewPayload):
    text: str = Field(min_length=1, max_length=4000)


class GenerationPayload(InterviewPayload):
    run_id: str = Field(alias='runId', min_length=1, max_length=36)


class EmptyPayload(InterviewPayload):
    pass


class CommandBase(InterviewPayload):
    client_message_id: str = Field(alias='clientMessageId', min_length=1, max_length=100)
    expected_turn: int = Field(alias='expectedTurn', ge=0, le=8)


class AnswerCommand(CommandBase):
    type: Literal['answer.submit']
    payload: AnswerPayload


class CancelCommand(CommandBase):
    type: Literal['generation.cancel']
    payload: GenerationPayload


class RetryCommand(CommandBase):
    type: Literal['generation.retry']
    payload: GenerationPayload


class FinishCommand(CommandBase):
    type: Literal['session.finish']
    payload: EmptyPayload


InterviewCommand = Annotated[AnswerCommand | CancelCommand | RetryCommand | FinishCommand,
                             Field(discriminator='type')]
INTERVIEW_COMMAND_ADAPTER = TypeAdapter(InterviewCommand)


class ConfirmInterviewMemory(InterviewPayload):
    confirmed: StrictBool
