from litellm.llms.gemini.chat.transformation import GoogleAIStudioGeminiConfig
from litellm.secret_managers.main import get_secret_str


class OminiLinkGeminiConfig(GoogleAIStudioGeminiConfig):
    @staticmethod
    def get_api_base(api_base: str | None = None) -> str:
        return api_base or get_secret_str("OMINILINK_GEMINI_API_BASE") or "https://api.ominilink.ai/v1beta"

    @staticmethod
    def get_api_key(api_key: str | None = None) -> str | None:
        return api_key or get_secret_str("OMINILINK_GEMINI_API_KEY")
