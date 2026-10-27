from litellm.llms.openai.chat.gpt_transformation import OpenAIGPTConfig
from litellm.secret_managers.main import get_secret_str


class ToAPIsChatConfig(OpenAIGPTConfig):
    def get_openai_compatible_provider_info(self, api_base: str | None, api_key: str | None) -> tuple[str, str | None]:
        return (
            api_base or get_secret_str("TOAPIS_API_BASE") or "https://toapis.com/v1",
            api_key or get_secret_str("TOAPIS_API_KEY"),
        )
