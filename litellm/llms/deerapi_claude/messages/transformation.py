from collections.abc import Mapping, Sequence
from typing import Final

from litellm.llms.anthropic.pass_through.messages.transformation import AnthropicMessagesConfig
from litellm.secret_managers.main import get_secret_str

DEFAULT_API_BASE: Final = "https://api.deerapi.com/v1/messages"


class DeerapiClaudeMessagesConfig(AnthropicMessagesConfig):
    @property
    def custom_llm_provider(self) -> str:
        return "deerapi_claude"

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
            or get_secret_str("DEERAPI_CLAUDE_API_BASE")
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
            or get_secret_str("DEERAPI_CLAUDE_API_KEY")
        )
        authorization: Final = (
            {"Authorization": f"Bearer {resolved_key}"}
            if resolved_key and not any(name.lower() == "authorization" for name in headers)
            else {}
        )
        return {"content-type": "application/json", **headers, **authorization}, api_base
