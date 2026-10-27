
def test_is_model_response_stream_empty():
    chunk = ModelResponseStream(
        id="chatcmpl-C3sWKN2RWbn6CZ1IGU2QCpRh4RhYf",
        created=1755040596,
        model="gpt-4o-mini",
        object="chat.completion.chunk",
        system_fingerprint="fp_34a54ae93c",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(
                    provider_specific_fields=None,
                    content=None,
                    role=None,
                    function_call=None,
                    tool_calls=None,
                    audio=None,
                ),
                logprobs=None,
            )
        ],
        provider_specific_fields=None,
    )
    assert is_model_response_stream_empty(chunk) is True


def test_is_model_response_stream_empty_with_custom_value():
    chunk = ModelResponseStream(
        id="chatcmpl-C3sWKN2RWbn6CZ1IGU2QCpRh4RhYf",
        created=1755040596,
        model="gpt-4o-mini",
        object="chat.completion.chunk",
        system_fingerprint="fp_34a54ae93c",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(
                    provider_specific_fields=None,
                    content=None,
                    role=None,
                    function_call=None,
                    tool_calls=None,
                    audio=None,
                ),
                logprobs=None,
            )
        ],
        provider_specific_fields=None,
    )

    setattr(chunk.choices[0].delta, "custom_field", "test")
    assert is_model_response_stream_empty(chunk) is False


from litellm.litellm_core_utils.model_response_utils import (
    is_model_response_stream_empty,
    validate_first_chat_completion_response,
)
from types import SimpleNamespace

import pytest

from litellm.exceptions import APIResponseValidationError
from litellm.types.utils import Delta, ModelResponse, ModelResponseStream, StreamingChoices


def test_validate_first_chat_completion_response_accepts_text():
    response = ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": "hello"}}],
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


@pytest.mark.parametrize("content", [None, "", "   "])
def test_validate_first_chat_completion_response_rejects_empty_text(content):
    response = ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": content}}],
    )

    with pytest.raises(APIResponseValidationError, match="empty completion response"):
        validate_first_chat_completion_response(
            model_response=response,
            model="gpt-4o-mini",
            llm_provider="openai",
        )


def test_validate_first_chat_completion_response_rejects_missing_choices():
    with pytest.raises(APIResponseValidationError, match="empty completion response"):
        validate_first_chat_completion_response(
            model_response=SimpleNamespace(choices=[]),
            model="gpt-4o-mini",
            llm_provider="openai",
        )


def test_validate_first_chat_completion_response_rejects_missing_message():
    with pytest.raises(APIResponseValidationError, match="empty completion response"):
        validate_first_chat_completion_response(
            model_response=SimpleNamespace(choices=[SimpleNamespace()]),
            model="gpt-4o-mini",
            llm_provider="openai",
        )


def test_validate_first_chat_completion_response_accepts_image_content_block():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example.com/image.png"},
                        }
                    ]
                )
            )
        ]
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_accepts_message_images():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    images=[
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://example.com/image.png"},
                        }
                    ],
                )
            )
        ]
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_accepts_tool_calls():
    response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "get_weather", "arguments": "{}"},
                        }
                    ],
                }
            }
        ],
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_accepts_function_call():
    response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {
                "message": {
                    "content": None,
                    "function_call": {
                        "name": "get_weather",
                        "arguments": "{}",
                    },
                }
            }
        ],
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_accepts_reasoning_content():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    reasoning_content="internal reasoning summary",
                )
            )
        ]
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_accepts_audio():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    audio={"id": "audio_123"},
                )
            )
        ]
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_accepts_thinking_blocks():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    thinking_blocks=[{"type": "thinking", "thinking": "step one"}],
                )
            )
        ]
    )

    assert validate_first_chat_completion_response(
        model_response=response,
        model="gpt-4o-mini",
        llm_provider="openai",
    ) is None


def test_validate_first_chat_completion_response_only_checks_first_choice():
    response = ModelResponse(
        model="gpt-4o-mini",
        choices=[
            {"message": {"content": "   "}},
            {"message": {"content": "fallback choice"}},
        ],
    )

    with pytest.raises(APIResponseValidationError, match="empty completion response"):
        validate_first_chat_completion_response(
            model_response=response,
            model="gpt-4o-mini",
            llm_provider="openai",
        )


@pytest.mark.parametrize("summary", ("Exact summary", "", "   "))
def test_chat_compaction_is_output_only_when_it_contains_a_summary(summary):
    response = ModelResponse(choices=[{
        "index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "",
            "provider_specific_fields": {"compaction_blocks": [{"type": "compaction", "content": summary, "signature": "opaque"}]},
        },
    }])
    if summary.strip():
        assert validate_first_chat_completion_response(response, "unit-model") is None
    else:
        with pytest.raises(APIResponseValidationError):
            validate_first_chat_completion_response(response, "unit-model")
