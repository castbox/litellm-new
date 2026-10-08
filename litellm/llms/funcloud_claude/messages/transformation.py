"""
FunCloud Claude provider implementation for Anthropic /v1/messages API

参考实现: litellm/llms/bedrock/messages/invoke_transformations/anthropic_claude3_transformation.py
后端调用 Bedrock，不支持 image URL，需将图片链接转为 base64。
"""
import copy
from typing import Any, Dict, List, Optional, Tuple

from litellm._logging import verbose_logger
from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.litellm_core_utils.prompt_templates.factory import (
    convert_to_anthropic_image_obj,
)
from litellm.litellm_core_utils.prompt_templates.image_handling import (
    convert_url_to_base64,
)
from litellm.secret_managers.main import get_secret_str
from litellm.types.router import GenericLiteLLMParams

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

    def transform_anthropic_messages_request(
        self,
        model: str,
        messages: List[Dict],
        anthropic_messages_optional_request_params: Dict,
        litellm_params: GenericLiteLLMParams,
        headers: dict,
    ) -> Dict:
        """
        先调用父类得到请求体，再将 messages 中 type=image 且 source.type=url 的图片转为 base64。
        后端为 Bedrock，不支持 image URL。
        """
        request = AnthropicMessagesConfig.transform_anthropic_messages_request(
            self=self,
            model=model,
            messages=messages,
            anthropic_messages_optional_request_params=anthropic_messages_optional_request_params,
            litellm_params=litellm_params,
            headers=headers,
        )
        messages_key = "messages"
        if messages_key not in request or not request[messages_key]:
            return request

        new_messages = []
        for msg in request[messages_key]:
            msg_copy = copy.deepcopy(msg)
            content = msg_copy.get("content")
            if not isinstance(content, list):
                new_messages.append(msg_copy)
                continue

            new_content = []
            for block in content:
                if not isinstance(block, dict):
                    new_content.append(block)
                    continue
                if block.get("type") != "image":
                    new_content.append(block)
                    continue
                source = block.get("source")
                if not isinstance(source, dict) or source.get("type") != "url":
                    new_content.append(block)
                    continue

                url = source.get("url")
                if not url or not isinstance(url, str):
                    new_content.append(block)
                    continue
                if not (url.startswith("http://") or url.startswith("https://")):
                    new_content.append(block)
                    continue

                try:
                    verbose_logger.debug(
                        "funcloud_claude: converting image url to base64, url=%s",
                        url[:100] + "..." if len(url) > 100 else url,
                    )
                    base64_uri = convert_url_to_base64(url=url)
                    image_chunk = convert_to_anthropic_image_obj(
                        openai_image_url=base64_uri, format=source.get("format")
                    )
                    new_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_chunk["media_type"],
                            "data": image_chunk["data"],
                        },
                    })
                    verbose_logger.debug(
                        "funcloud_claude: image url converted to base64, media_type=%s",
                        image_chunk["media_type"],
                    )
                except Exception as e:
                    verbose_logger.error(
                        "funcloud_claude: failed to convert image url to base64 (Bedrock requires base64), url=%s, error=%s",
                        url[:100] + "..." if len(url) > 100 else url,
                        e,
                    )
                    raise

            msg_copy["content"] = new_content
            new_messages.append(msg_copy)

        request = copy.deepcopy(request)
        request[messages_key] = new_messages
        return request
