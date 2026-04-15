from typing import Optional
from litellm.llms.gemini.chat.transformation import GoogleAIStudioGeminiConfig
from litellm.secret_managers.main import get_secret_str


class OminiLinkGeminiConfig(GoogleAIStudioGeminiConfig):
    """
    继承 GoogleAIStudioGeminiConfig，复用所有 Gemini 协议实现，
    只覆盖 API Base 和 API Key 获取逻辑。
    """

    @staticmethod
    def get_api_base(api_base: Optional[str] = None) -> str:
        return (
            api_base
            or get_secret_str("OMINILINK_GEMINI_API_BASE")
            or "https://api.ominilink.ai/v1beta"
        )

    @staticmethod
    def get_api_key(api_key: Optional[str] = None) -> Optional[str]:
        return api_key or get_secret_str("OMINILINK_GEMINI_API_KEY")
