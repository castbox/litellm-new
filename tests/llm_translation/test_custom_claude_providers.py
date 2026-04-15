import os
import sys
from unittest.mock import patch

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path

import litellm
from litellm.litellm_core_utils.prompt_templates.factory import anthropic_messages_pt
from litellm.llms.deerapi_claude.messages.transformation import (
    DeerapiClaudeMessagesConfig,
)
from litellm.llms.funcloud_claude.messages.transformation import (
    FuncloudClaudeMessagesConfig,
)
from litellm.utils import ProviderConfigManager


def test_custom_claude_providers_use_anthropic_chat_config():
    funcloud_config = ProviderConfigManager.get_provider_chat_config(
        model="claude-sonnet-4-5",
        provider=litellm.LlmProviders.FUNCLOUD_CLAUDE,
    )
    deerapi_config = ProviderConfigManager.get_provider_chat_config(
        model="claude-sonnet-4-5",
        provider=litellm.LlmProviders.DEERAPI_CLAUDE,
    )

    assert isinstance(funcloud_config, litellm.AnthropicConfig)
    assert isinstance(deerapi_config, litellm.AnthropicConfig)


def test_custom_claude_providers_use_custom_messages_configs():
    funcloud_config = ProviderConfigManager.get_provider_anthropic_messages_config(
        model="claude-sonnet-4-5",
        provider=litellm.LlmProviders.FUNCLOUD_CLAUDE,
    )
    deerapi_config = ProviderConfigManager.get_provider_anthropic_messages_config(
        model="claude-sonnet-4-5",
        provider=litellm.LlmProviders.DEERAPI_CLAUDE,
    )

    assert isinstance(funcloud_config, FuncloudClaudeMessagesConfig)
    assert isinstance(deerapi_config, DeerapiClaudeMessagesConfig)


@patch("litellm.litellm_core_utils.prompt_templates.factory.convert_url_to_base64")
def test_funcloud_claude_converts_image_urls_to_base64(mock_convert_url):
    mock_convert_url.return_value = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ=="

    result = anthropic_messages_pt(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/image.jpg"},
                    },
                ],
            }
        ],
        model="claude-sonnet-4-5",
        llm_provider="funcloud_claude",
    )

    mock_convert_url.assert_called_once_with(url="https://example.com/image.jpg")
    assert result[0]["content"][1]["source"]["type"] == "base64"


@patch("litellm.litellm_core_utils.prompt_templates.factory.anthropic_messages_pt")
def test_anthropic_config_uses_custom_llm_provider_from_litellm_params(
    mock_anthropic_messages_pt,
):
    mock_anthropic_messages_pt.return_value = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    ]

    config = litellm.AnthropicConfig()
    request = config.transform_request(
        model="claude-sonnet-4-5",
        messages=[{"role": "user", "content": "hi"}],
        optional_params={},
        litellm_params={"custom_llm_provider": "funcloud_claude"},
        headers={},
    )

    assert request["messages"] == mock_anthropic_messages_pt.return_value
    mock_anthropic_messages_pt.assert_called_once()
    assert mock_anthropic_messages_pt.call_args.kwargs["llm_provider"] == "funcloud_claude"
