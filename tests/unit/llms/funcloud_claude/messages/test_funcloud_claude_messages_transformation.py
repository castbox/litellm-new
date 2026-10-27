import base64
import copy
from typing import Final

import httpx
import pytest

import litellm
from litellm.llms.funcloud_claude.messages.transformation import FuncloudClaudeMessagesConfig
from litellm.types.router import GenericLiteLLMParams

_PNG: Final = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+y4f8AAAAASUVORK5CYII="
)


def test_messages_inlines_images_without_mutating_the_callers_request(monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "user_url_validation", False)
    url: Final = "https://images.test/funcloud-message.png"
    route: Final = respx_mock.get(url).respond(200, content=_PNG, headers={"content-type": "image/png"})
    messages: Final = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe"},
                {"type": "image", "source": {"type": "url", "url": url}},
            ],
        }
    ]
    original: Final = copy.deepcopy(messages)
    options: Final = {"max_tokens": 32, "temperature": 0.5}
    result: Final = FuncloudClaudeMessagesConfig().transform_anthropic_messages_request(
        model="unit-model",
        messages=messages,
        anthropic_messages_optional_request_params=options,
        litellm_params=GenericLiteLLMParams(),
        headers={},
    )
    assert result["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(_PNG).decode()},
                },
            ],
        }
    ]
    assert messages == original
    assert options == {"max_tokens": 32, "temperature": 0.5}
    assert route.call_count == 1


def test_messages_reports_image_download_failure(monkeypatch, respx_mock):
    monkeypatch.setattr(litellm, "user_url_validation", False)
    url: Final = "https://images.test/funcloud-denied.png"
    respx_mock.get(url).respond(403)
    with pytest.raises(litellm.ImageFetchError):
        FuncloudClaudeMessagesConfig().transform_anthropic_messages_request(
            model="unit-model",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "url", "url": url}},
                    ],
                }
            ],
            anthropic_messages_optional_request_params={"max_tokens": 32},
            litellm_params=GenericLiteLLMParams(),
            headers={},
        )
