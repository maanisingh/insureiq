"""
BedrockChatCompletionClient — AutoGen 0.4+ ChatCompletionClient backed by AWS Bedrock.

Supports:
  - Bedrock Claude 3.5 Sonnet v2  (chat + tool calling)
  - Full tool/function-calling support (converts AutoGen ↔ Bedrock format)
  - Token counting (approximation)
  - Streaming stub (yields full response as one chunk)
"""

import os
import json
import asyncio
import warnings
from typing import Any, AsyncGenerator, Literal, Mapping, Optional, Sequence, Union
from pathlib import Path

import boto3
from dotenv import load_dotenv

from autogen_core import FunctionCall, CancellationToken
from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    FinishReasons,
    LLMMessage,
    ModelFamily,
    ModelInfo,
    ModelCapabilities,
    RequestUsage,
    SystemMessage,
    UserMessage,
    AssistantMessage,
    FunctionExecutionResultMessage,
)
from autogen_core.tools import Tool, ToolSchema

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

CHAT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
CTX_WINDOW  = 200_000  # Claude 3.5 Sonnet context window (tokens)


class BedrockChatCompletionClient(ChatCompletionClient):
    """AWS Bedrock Claude 3.5 Sonnet model client for AutoGen 0.4+.

    Usage:
        client = BedrockChatCompletionClient()
        result = await client.create(messages=[...], tools=[...])
    """

    def __init__(
        self,
        model: str = CHAT_MODEL,
        max_tokens: int = 4096,
        region: str | None = None,
    ):
        self._model      = model
        self._max_tokens = max_tokens
        self._region     = region or os.getenv("AWS_REGION", "us-east-1")
        self._usage      = RequestUsage(prompt_tokens=0, completion_tokens=0)
        self._total      = RequestUsage(prompt_tokens=0, completion_tokens=0)
        self._client     = self._make_client()

    def _make_client(self):
        kwargs: dict[str, Any] = {"region_name": self._region}
        key    = os.getenv("AWS_ACCESS_KEY_ID")
        secret = os.getenv("AWS_SECRET_ACCESS_KEY")
        if key and secret:
            kwargs["aws_access_key_id"]     = key
            kwargs["aws_secret_access_key"] = secret
        return boto3.client("bedrock-runtime", **kwargs)

    # ── Message format conversion ─────────────────────────────────────────────

    def _to_bedrock_messages(
        self, messages: Sequence[LLMMessage]
    ) -> tuple[str, list[dict]]:
        """Convert AutoGen LLMMessages to Bedrock (system, messages) format."""
        system  = ""
        bedrock = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system = msg.content
            elif isinstance(msg, UserMessage):
                content = msg.content
                if isinstance(content, str):
                    # Bedrock rejects empty text blocks — use placeholder if empty
                    text = content.strip() or "..."
                    bedrock.append({"role": "user", "content": [{"type": "text", "text": text}]})
                else:
                    # Multimodal content list — pass through, guard empties
                    safe = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            if not block.get("text", "").strip():
                                block = {**block, "text": "..."}
                        safe.append(block)
                    bedrock.append({"role": "user", "content": safe})

            elif isinstance(msg, AssistantMessage):
                if isinstance(msg.content, str):
                    text = msg.content.strip()
                    if not text:
                        text = "..."  # Bedrock requires non-empty, non-whitespace content
                    bedrock.append({
                        "role": "assistant",
                        "content": [{"type": "text", "text": text}],
                    })
                else:
                    # FunctionCall list
                    content_parts = []
                    for fc in msg.content:
                        content_parts.append({
                            "type":  "tool_use",
                            "id":    fc.id,
                            "name":  fc.name,
                            "input": json.loads(fc.arguments),
                        })
                    bedrock.append({"role": "assistant", "content": content_parts})

            elif isinstance(msg, FunctionExecutionResultMessage):
                tool_results = []
                for res in msg.content:
                    # Bedrock requires non-empty tool result content
                    result_content = res.content if res.content and res.content.strip() else "..."
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": res.call_id,
                        "content":     result_content,
                    })
                bedrock.append({"role": "user", "content": tool_results})

        return system, bedrock

    def _ensure_valid_turn_order(self, messages: list[dict]) -> list[dict]:
        """Ensure messages have valid turn order for Bedrock API.

        Some newer models (Sonnet 4.6, Opus 4.6+) do not support assistant
        message prefill — the conversation must end with a user message.
        Also ensures no consecutive same-role messages (merges them).
        """
        if not messages:
            return messages

        # Merge consecutive same-role messages
        merged = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                # Merge content arrays
                merged[-1]["content"].extend(msg["content"])
            else:
                merged.append(msg)

        # Ensure conversation ends with user message
        if merged and merged[-1]["role"] == "assistant":
            merged.append({
                "role": "user",
                "content": [{"type": "text", "text": "Please continue with your response."}],
            })

        # Ensure conversation starts with user message
        if merged and merged[0]["role"] == "assistant":
            merged.insert(0, {
                "role": "user",
                "content": [{"type": "text", "text": "Please proceed."}],
            })

        return merged

    def _to_bedrock_tools(self, tools: Sequence[Tool | ToolSchema]) -> list[dict]:
        """Convert AutoGen Tool/ToolSchema list to Bedrock tool definitions."""
        bedrock_tools = []
        for tool in tools:
            if isinstance(tool, Tool):
                schema = tool.schema
            else:
                schema = tool  # already a ToolSchema dict

            # Extract parameters — AutoGen schema follows JSON Schema
            params = schema.get("parameters", {})

            bedrock_tools.append({
                "name":         schema["name"],
                "description":  schema.get("description", ""),
                "input_schema": params if params else {"type": "object", "properties": {}},
            })
        return bedrock_tools

    # ── Main create ───────────────────────────────────────────────────────────

    async def create(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | Literal["auto", "required", "none"] = "auto",
        json_output: Optional[bool | type] = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: Optional[CancellationToken] = None,
    ) -> CreateResult:
        system, bedrock_messages = self._to_bedrock_messages(messages)
        bedrock_messages = self._ensure_valid_turn_order(bedrock_messages)

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        self._max_tokens,
            "messages":          bedrock_messages,
        }
        if system:
            body["system"] = system

        if tools:
            body["tools"] = self._to_bedrock_tools(tools)
            if tool_choice == "none":
                body["tool_choice"] = {"type": "auto"}  # Bedrock has no "none" equivalent
            elif tool_choice == "required":
                body["tool_choice"] = {"type": "any"}
            else:
                body["tool_choice"] = {"type": "auto"}

        # Run in executor so we don't block the event loop
        loop     = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.invoke_model(
                modelId=self._model,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            ),
        )
        result = json.loads(response["body"].read())

        # Track usage
        usage = RequestUsage(
            prompt_tokens=result.get("usage", {}).get("input_tokens", 0),
            completion_tokens=result.get("usage", {}).get("output_tokens", 0),
        )
        self._usage = usage
        self._total = RequestUsage(
            prompt_tokens=self._total.prompt_tokens + usage.prompt_tokens,
            completion_tokens=self._total.completion_tokens + usage.completion_tokens,
        )

        stop_reason = result.get("stop_reason", "end_turn")

        # Parse content blocks
        content_blocks = result.get("content", [])
        text_parts     = []
        tool_calls     = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append(FunctionCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=json.dumps(block.get("input", {})),
                ))

        if tool_calls:
            content: str | list[FunctionCall] = tool_calls
            finish: FinishReasons = "function_calls"
        else:
            content = "\n".join(text_parts) if text_parts else ""
            finish  = "stop"

        return CreateResult(
            finish_reason=finish,
            content=content,
            usage=usage,
            cached=False,
        )

    # ── Streaming (minimal — yields full result) ──────────────────────────────

    async def create_stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
        tool_choice: Tool | Literal["auto", "required", "none"] = "auto",
        json_output: Optional[bool | type] = None,
        extra_create_args: Mapping[str, Any] = {},
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AsyncGenerator[Union[str, CreateResult], None]:
        result = await self.create(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            json_output=json_output,
            extra_create_args=extra_create_args,
            cancellation_token=cancellation_token,
        )
        if isinstance(result.content, str):
            yield result.content
        yield result

    # ── Token counting ────────────────────────────────────────────────────────

    def count_tokens(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
    ) -> int:
        """Approximate token count (4 chars ≈ 1 token)."""
        total = 0
        for msg in messages:
            if hasattr(msg, "content"):
                c = msg.content
                total += len(c if isinstance(c, str) else json.dumps(c)) // 4
        for tool in tools:
            schema = tool.schema if isinstance(tool, Tool) else tool
            total += len(json.dumps(schema)) // 4
        return total

    def remaining_tokens(
        self,
        messages: Sequence[LLMMessage],
        *,
        tools: Sequence[Tool | ToolSchema] = [],
    ) -> int:
        return max(0, CTX_WINDOW - self.count_tokens(messages, tools=tools))

    # ── Metadata ──────────────────────────────────────────────────────────────

    @property
    def model_info(self) -> ModelInfo:
        # Determine family from model ID
        if "opus" in self._model:
            family = ModelFamily.UNKNOWN
        elif "haiku" in self._model:
            family = ModelFamily.UNKNOWN
        else:
            family = ModelFamily.UNKNOWN
        return ModelInfo(
            vision=True,
            function_calling=True,
            json_output=True,
            family=family,
            structured_output=False,
        )

    @property
    def capabilities(self) -> ModelCapabilities:  # type: ignore[override]
        return ModelCapabilities(
            vision=True,
            function_calling=True,
            json_output=True,
        )

    def actual_usage(self) -> RequestUsage:
        return self._usage

    def total_usage(self) -> RequestUsage:
        return self._total

    async def close(self) -> None:
        """No persistent connection to close."""
        pass

    # ── ComponentBase required serialisation stubs ────────────────────────────

    def _to_config(self) -> dict:
        return {"model": self._model, "max_tokens": self._max_tokens, "region": self._region}

    @classmethod
    def _from_config(cls, config: dict) -> "BedrockChatCompletionClient":
        return cls(**config)
