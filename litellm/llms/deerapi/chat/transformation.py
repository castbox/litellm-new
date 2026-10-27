from collections.abc import Mapping
from typing import Final

from litellm.llms.openai.chat.gpt_transformation import OpenAIGPTConfig
from litellm.secret_managers.main import get_secret_str


class DeerAPIChatConfig(OpenAIGPTConfig):
    def get_openai_compatible_provider_info(self, api_base: str | None, api_key: str | None) -> tuple[str, str | None]:
        return (
            api_base or get_secret_str("DEERAPI_API_BASE") or "https://api.deerapi.com/v1",
            api_key or get_secret_str("DEERAPI_API_KEY") or get_secret_str("DEER_API_KEY"),
        )

    def get_complete_url(
        self,
        api_base: str | None,
        api_key: str | None,
        model: str,
        optional_params: Mapping[str, object],
        litellm_params: Mapping[str, object],
        stream: bool | None = None,
    ) -> str:
        resolved_base: Final = self.get_openai_compatible_provider_info(api_base, api_key)[0].rstrip("/")
        return resolved_base if resolved_base.endswith("/chat/completions") else f"{resolved_base}/chat/completions"
