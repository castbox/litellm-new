"""
DeerAPI Gemini transformation - 使用 Gemini 协议但自定义域名
"""
from typing import Optional

from litellm.llms.gemini.chat.transformation import GoogleAIStudioGeminiConfig
from litellm.secret_managers.main import get_secret_str


class DeerAPIGeminiConfig(GoogleAIStudioGeminiConfig):
    """
    DeerAPI Gemini 配置类

    继承 GoogleAIStudioGeminiConfig，复用所有 Gemini 协议实现，
    只覆盖 API Base 和 API Key 获取逻辑。
    """

    @staticmethod
    def get_api_base(api_base: Optional[str] = None) -> str:
        """获取 API Base URL"""
        return (
            api_base
            or get_secret_str("DEERAPI_GEMINI_API_BASE")
            or "https://api.deerapi.com/v1beta"
        )

    @staticmethod
    def get_api_key(api_key: Optional[str] = None) -> Optional[str]:
        """获取 API Key"""
        return (
            api_key
            or get_secret_str("DEERAPI_GEMINI_API_KEY")
            or get_secret_str("DEERAPI_API_KEY")
        )
