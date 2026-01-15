import os
import sys
import pytest

# Adds the parent directory to the system path
sys.path.insert(0, os.path.abspath("../../../../.."))

from litellm.llms.deerapi.chat.transformation import DeerAPIChatConfig

TEST_API_KEY = "test_deerapi_api_key"
TEST_MODEL_NAME = "gpt-3.5-turbo"
TEST_MODEL = f"deerapi/{TEST_MODEL_NAME}"
TEST_MESSAGES = [{"role": "user", "content": "Hello"}]


class TestDeerAPIChatConfig:
    def test_validate_environment(self):
        """测试环境验证功能"""
        config = DeerAPIChatConfig()

        headers = {}

        result = config.validate_environment(
            headers=headers,
            model=TEST_MODEL,
            messages=TEST_MESSAGES,  # type: ignore
            optional_params={},
            litellm_params={},
            api_key=TEST_API_KEY,
            api_base="https://api.deerapi.com/v1",
        )

        assert result["Authorization"] == f"Bearer {TEST_API_KEY}"
        assert result["Content-Type"] == "application/json"

    def test_missing_api_key(self):
        """测试缺少 API key 的错误处理"""
        config = DeerAPIChatConfig()
        
        # Test that _get_openai_compatible_provider_info returns None for api_key when not set
        api_base, api_key = config._get_openai_compatible_provider_info(None, None)
        assert api_base == "https://api.deerapi.com/v1"  # Should have default
        assert api_key is None  # Should be None when not provided


    def test_get_complete_url(self):
        """测试完整 URL 生成"""
        config = DeerAPIChatConfig()

        # 测试默认 API base
        url = config.get_complete_url(
            api_base=None,
            api_key=TEST_API_KEY,
            model=TEST_MODEL_NAME,
            optional_params={},
            litellm_params={},
        )
        
        assert url == "https://api.deerapi.com/v1/chat/completions"

        # 测试自定义 API base
        custom_base = "https://custom.api.com/v1"
        url = config.get_complete_url(
            api_base=custom_base,
            api_key=TEST_API_KEY,
            model=TEST_MODEL_NAME,
            optional_params={},
            litellm_params={},
        )
        
        assert url == f"{custom_base}/chat/completions"

    def test_deerapi_completion_mock_sync(self, respx_mock):
        """测试同步完成调用（使用 mock）"""
        import litellm

        input_messages = [
            {"role": "user", "content": "What is your favorite kind of cat?"}
        ]

        output_content = "Hello, how can I help you today?"

        # Mock the HTTP request - 使用 OpenAI 格式的响应
        respx_mock.post("https://api.deerapi.com/v1/chat/completions").respond(
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1234567890,
                "model": TEST_MODEL_NAME,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": output_content,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            },
            status_code=200,
        )

        # 通过 LiteLLM 进行实际的 API 调用
        response = litellm.completion(
            model=TEST_MODEL,
            messages=input_messages,
            api_key=TEST_API_KEY,
            api_base="https://api.deerapi.com/v1",
        )

        assert response.choices[0].message.content == output_content  # type: ignore
        assert response.model.startswith("deerapi/")  # 确保模型名称有正确的前缀

    def test_get_openai_compatible_provider_info(self):
        """测试 OpenAI 兼容的 provider 信息获取"""
        config = DeerAPIChatConfig()

        # 测试默认值
        api_base, api_key = config._get_openai_compatible_provider_info(
            api_base=None, api_key=None
        )
        
        assert api_base == "https://api.deerapi.com/v1"
        assert api_key is None  # 应该为 None 当没有提供时

        # 测试自定义值
        custom_base = "https://custom.deerapi.com/v1"
        custom_key = "custom_key"
        
        api_base, api_key = config._get_openai_compatible_provider_info(
            api_base=custom_base, api_key=custom_key
        )
        
        assert api_base == custom_base
        assert api_key == custom_key

