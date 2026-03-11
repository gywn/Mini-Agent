"""OpenAI LLM client implementation."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from ..retry import RetryConfig, async_retry
from ..schema import FunctionCall, LLMResponse, Message, TokenUsage, ToolCall
from ..schema.schema import AssistantMessage, SystemMessage, ToolResultMessage, UserMessage
from .base import LLMClientBase

if TYPE_CHECKING:
    from ..tools.base import Tool

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClientBase):
    """LLM client using OpenAI's protocol.

    This client uses the official OpenAI SDK and supports:
    - Reasoning content (via reasoning_split=True)
    - Tool calling
    - Retry logic
    """

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimaxi.com/v1",
        model: str = "MiniMax-M2.5",
        retry_config: RetryConfig | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: API key for authentication
            api_base: Base URL for the API (default: MiniMax OpenAI endpoint)
            model: Model name to use (default: MiniMax-M2.5)
            retry_config: Optional retry configuration
        """
        super().__init__(api_key, api_base, model, retry_config)

        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
        )

    async def _make_api_request(
        self,
        api_messages: list[dict[str, Any]],
        tools: list[Tool] | None = None,
    ) -> Any:
        """Execute API request (core method that can be retried).

        Args:
            api_messages: List of messages in OpenAI format
            tools: Optional list of tools

        Returns:
            OpenAI ChatCompletion response (full response including usage)

        Raises:
            Exception: API call failed
        """
        params = {
            "model": self.model,
            "messages": api_messages,
            # Enable reasoning_split to separate thinking content
            "extra_body": {"reasoning_split": True},
        }

        if tools:
            params["tools"] = self._convert_tools(tools)

        # Use OpenAI SDK's chat.completions.create
        response = await self.client.chat.completions.create(**params)  # type: ignore[call-overload]
        # Return full response to access usage info
        return response

    def _convert_tools(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Convert tools to OpenAI format.

        Args:
            tools: List of Tool objects

        Returns:
            List of tools in OpenAI dict format
        """
        result: list[dict[str, Any]] = []
        for tool in tools:
            if hasattr(tool, "to_openai_schema"):
                # Tool object with to_openai_schema method
                result.append(tool.to_openai_schema())
            else:
                raise TypeError(f"Unsupported tool type: {type(tool)}")
        return result

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert internal messages to OpenAI format.

        Args:
            messages: List of internal Message objects

        Returns:
            Tuple of (system_message, api_messages)
            Note: OpenAI includes system message in the messages array
        """
        api_messages = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                # OpenAI includes system message in messages array
                api_messages.append({"role": "system", "content": msg.content})
                continue

            # For user messages
            elif isinstance(msg, UserMessage):
                api_messages.append({"role": "user", "content": msg.content})

            # For assistant messages
            elif isinstance(msg, AssistantMessage):
                assistant_msg: dict[str, Any] = {"role": "assistant"}

                # Add content if present
                if msg.content:
                    assistant_msg["content"] = msg.content

                # Add tool calls if present
                if msg.tool_calls:
                    tool_calls_list: list[dict[str, Any]] = []
                    for tool_call in msg.tool_calls:
                        tool_calls_list.append(
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": json.dumps(tool_call.function.arguments),
                                },
                            }
                        )
                    assistant_msg["tool_calls"] = tool_calls_list

                # IMPORTANT: Add reasoning_details if thinking is present
                # This is CRITICAL for Interleaved Thinking to work properly!
                # The complete response_message (including reasoning_details) must be
                # preserved in Message History and passed back to the model in the next turn.
                # This ensures the model's chain of thought is not interrupted.
                if msg.thinking:
                    assistant_msg["reasoning_details"] = [{"text": msg.thinking}]

                api_messages.append(assistant_msg)

            # For tool result messages
            elif isinstance(msg, ToolResultMessage):
                tool_msg: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                }
                api_messages.append(tool_msg)

        return None, api_messages

    def _prepare_request(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
    ) -> dict[str, Any]:
        """Prepare the request for OpenAI API.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            Dictionary containing request parameters
        """
        _, api_messages = self._convert_messages(messages)

        return {
            "api_messages": api_messages,
            "tools": tools,
        }

    def _parse_response(self, response: ChatCompletion) -> LLMResponse:
        """Parse OpenAI response into LLMResponse.

        Args:
            response: OpenAI ChatCompletion response (full response object)

        Returns:
            LLMResponse object
        """
        # Get message from response
        message = response.choices[0].message

        # Extract text content
        text_content = message.content or ""

        # Extract thinking content from reasoning_details
        thinking_content = ""
        if hasattr(message, "reasoning_details") and message.reasoning_details:
            # reasoning_details is a list of reasoning blocks
            for detail in message.reasoning_details:
                if hasattr(detail, "text"):
                    thinking_content += detail.text

        # Extract tool calls
        tool_calls = []
        if message.tool_calls:
            for tool_call in message.tool_calls:
                # Handle both function and custom tool calls
                if hasattr(tool_call, "function") and tool_call.function:
                    # Parse arguments from JSON string
                    arguments = json.loads(tool_call.function.arguments)

                    tool_calls.append(
                        ToolCall(
                            id=tool_call.id,
                            type="function",
                            function=FunctionCall(
                                name=tool_call.function.name,
                                arguments=arguments,
                            ),
                        )
                    )

        # Extract token usage from response
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            )

        return LLMResponse(
            content=text_content,
            thinking=thinking_content if thinking_content else None,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason="stop",  # OpenAI doesn't provide finish_reason in the message
            usage=usage,
        )

    async def generate(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
    ) -> LLMResponse:
        """Generate response from OpenAI LLM.

        Args:
            messages: List of conversation messages
            tools: Optional list of available tools

        Returns:
            LLMResponse containing the generated content
        """
        # Prepare request
        request_params = self._prepare_request(messages, tools)

        # Make API request with retry logic
        if self.retry_config.enabled:
            # Apply retry logic
            retry_decorator = async_retry(config=self.retry_config, on_retry=self.retry_callback)
            api_call = retry_decorator(self._make_api_request)
            response = await api_call(
                request_params["api_messages"],
                request_params["tools"],
            )
        else:
            # Don't use retry
            response = await self._make_api_request(
                request_params["api_messages"],
                request_params["tools"],
            )

        # Parse and return response
        return self._parse_response(response)
