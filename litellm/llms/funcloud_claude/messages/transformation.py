import copy
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import JsonValue, TypeAdapter

from litellm.litellm_core_utils.prompt_templates.factory import convert_to_anthropic_image_obj
from litellm.llms.anthropic.pass_through.messages.transformation import AnthropicMessagesConfig
from litellm.secret_managers.main import get_secret_str
from litellm.types.router import GenericLiteLLMParams

_JSON_REQUEST: Final = TypeAdapter(Mapping[str, JsonValue])

DEFAULT_API_BASE: Final = "https://funcloud.ai/v1/model/chat/completions"


class FuncloudClaudeMessagesConfig(AnthropicMessagesConfig):
    @property
    def custom_llm_provider(self) -> str:
        return "funcloud_claude"

    def get_complete_url(
        self,
        api_base: str | None,
        api_key: str | None,
        model: str,
        optional_params: Mapping[str, object],
        litellm_params: Mapping[str, object],
        stream: bool | None = None,
    ) -> str:
        configured_base: Final = litellm_params.get("api_base")
        resolved_base: Final = (
            api_base
            or (configured_base if isinstance(configured_base, str) else None)
            or get_secret_str("FUNCLOUD_CLAUDE_API_BASE")
            or DEFAULT_API_BASE
        )
        return resolved_base.rstrip("/")

    def validate_anthropic_messages_environment(
        self,
        headers: Mapping[str, str],
        model: str,
        messages: Sequence[object],
        optional_params: Mapping[str, object],
        litellm_params: Mapping[str, object],
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> tuple[dict[str, str], str | None]:  # mutable-ok: the base HTTP handler requires a header dictionary
        configured_key: Final = litellm_params.get("api_key")
        resolved_key: Final = (
            api_key
            or (configured_key if isinstance(configured_key, str) else None)
            or get_secret_str("FUNCLOUD_CLAUDE_API_KEY")
        )
        authorization: Final = (
            {"Authorization": f"Bearer {resolved_key}"}
            if resolved_key and not any(name.lower() == "authorization" for name in headers)
            else {}
        )
        return {"content-type": "application/json", **headers, **authorization}, api_base

    @staticmethod
    def _inline_image(block: JsonValue) -> JsonValue:
        if not isinstance(block, dict) or block.get("type") != "image":
            return block
        source: Final = block.get("source")
        if not isinstance(source, dict) or source.get("type") != "url":
            return block
        url: Final = source.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return block
        format_hint: Final = source.get("format")
        image: Final = convert_to_anthropic_image_obj(url, format=format_hint if isinstance(format_hint, str) else None)
        return {**block, "source": {"type": "base64", "media_type": image["media_type"], "data": image["data"]}}

    def _inline_message(self, message: JsonValue) -> JsonValue:
        if not isinstance(message, dict):
            return message
        content: Final = message.get("content")
        if not isinstance(content, list):
            return message
        return {**message, "content": [self._inline_image(block) for block in content]}

    def transform_anthropic_messages_request(
        self,
        model: str,
        messages: Sequence[Mapping[str, JsonValue]],
        anthropic_messages_optional_request_params: Mapping[str, object],
        litellm_params: GenericLiteLLMParams,
        headers: Mapping[str, str],
    ) -> dict[str, JsonValue]:  # mutable-ok: the base HTTP handler serializes a request dictionary
        request: Final = _JSON_REQUEST.validate_python(
            super().transform_anthropic_messages_request(
                model=model,
                messages=[copy.deepcopy(dict(message)) for message in messages],
                anthropic_messages_optional_request_params=copy.deepcopy(
                    dict(anthropic_messages_optional_request_params)
                ),
                litellm_params=litellm_params,
                headers=dict(headers),
            )
        )
        request_messages: Final = request.get("messages")
        if not isinstance(request_messages, list):
            return dict(request)
        return {**request, "messages": [self._inline_message(message) for message in request_messages]}
