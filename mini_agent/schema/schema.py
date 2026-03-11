from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel


class LLMProvider(str, Enum):
    """LLM provider types."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class FunctionCall(BaseModel):
    """Function call details."""

    name: str
    arguments: dict[str, Any]  # Function arguments as dict


class ToolCall(BaseModel):
    """Tool call structure."""

    id: str
    type: str  # "function"
    function: FunctionCall


class SystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    thinking: str | None
    content: str | None
    tool_calls: list[ToolCall] | None


class ToolResultMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str
    name: str


Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolResultMessage]


class TokenUsage(BaseModel):
    """Token usage statistics from LLM API response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """LLM response."""

    content: str
    thinking: str | None = None  # Extended thinking blocks
    tool_calls: list[ToolCall] | None = None
    finish_reason: str
    usage: TokenUsage | None = None  # Token usage from API response
