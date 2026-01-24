"""
FunCloud Claude provider implementation for Anthropic /v1/messages API

参考实现: litellm/llms/bedrock/messages/invoke_transformations/anthropic_claude3_transformation.py
"""
from typing import Any, List, Optional, Tuple

from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.secret_managers.main import get_secret_str

# 默认 API 地址（包含完整路径）
DEFAULT_API_BASE = "https://funcloud.ai/v1/model/chat/completions"


class FuncloudClaudeMessagesConfig(AnthropicMessagesConfig):
    """
    FunCloud Claude provider implementation for Anthropic /v1/messages API

    继承自 AnthropicMessagesConfig，自动复用：
    - get_supported_anthropic_messages_params: 支持的参数列表
    - transform_anthropic_messages_request: 请求转换
    - transform_anthropic_messages_response: 响应转换
    - get_async_streaming_response_iterator: 流式响应处理

    只需覆盖：
    - get_complete_url: 构建 API URL
    - validate_anthropic_messages_environment: 设置认证 headers

    支持的 deployment 配置参数（通过 litellm_params 传递）：
    - api_base: API 完整地址（包含路径）
    - api_key: API 密钥
    """

    def get_complete_url(
        self,
        api_base: Optional[str],
        api_key: Optional[str],
        model: str,
        optional_params: dict,
        litellm_params: dict,
        stream: Optional[bool] = None,
    ) -> str:
        """构建 API URL"""
        api_base = (
            api_base
            or litellm_params.get("api_base")
            or get_secret_str("FUNCLOUD_CLAUDE_API_BASE")
            or DEFAULT_API_BASE
        )
        return api_base.rstrip("/")

    def validate_anthropic_messages_environment(
        self,
        headers: dict,
        model: str,
        messages: List[Any],
        optional_params: dict,
        litellm_params: dict,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> Tuple[dict, Optional[str]]:
        """设置认证 headers - 使用 Bearer Token 认证"""
        if api_key is None:
            api_key = (
                litellm_params.get("api_key")
                or get_secret_str("FUNCLOUD_CLAUDE_API_KEY")
            )

        # FunCloud Claude 使用 Bearer Token 认证
        if "Authorization" not in headers and api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if "content-type" not in headers:
            headers["content-type"] = "application/json"

        return headers, api_base
