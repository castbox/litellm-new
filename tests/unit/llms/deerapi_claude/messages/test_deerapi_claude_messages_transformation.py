import litellm
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


def test_funcloud_chat_inlines_image_data_with_its_provider(monkeypatch, respx_mock):
    import base64

    monkeypatch.setattr(litellm, "user_url_validation", False)
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+y4f8AAAAASUVORK5CYII="
    )
    url = "https://images.test/funcloud-chat.png"
    image_route = respx_mock.get(url).respond(200, content=image_bytes, headers={"content-type": "image/png"})

    request = litellm.AnthropicConfig().transform_request(
        model="unit-model",
        messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]}],
        optional_params={"max_tokens": 32},
        litellm_params={"custom_llm_provider": "funcloud_claude"},
        headers={},
    )

    assert request["messages"][0]["content"][0]["source"] == {
        "type": "base64", "media_type": "image/png", "data": base64.b64encode(image_bytes).decode(),
    }
    assert image_route.call_count == 1
