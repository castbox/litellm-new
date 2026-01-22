"""
Translates from OpenAI's `/v1/chat/completions` to ToAPIs's `/v1/chat/completions`
"""
from typing import Optional, Tuple
from litellm.secret_managers.main import get_secret_str
from ...openai.chat.gpt_transformation import OpenAIGPTConfig


class ToAPIsChatConfig(OpenAIGPTConfig):
    def _get_openai_compatible_provider_info(
        self, api_base: Optional[str], api_key: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        api_base = (
            api_base
            or get_secret_str("TOAPIS_API_BASE")
            or "https://toapis.com/v1"
        )
        dynamic_api_key = (
            api_key
            or get_secret_str("TOAPIS_API_KEY")
        )
        return api_base, dynamic_api_key
