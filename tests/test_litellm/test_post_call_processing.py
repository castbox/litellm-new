from unittest.mock import MagicMock

import pytest

from litellm.exceptions import APIResponseValidationError
from litellm.types.llms.openai import ResponsesAPIResponse
from litellm.types.utils import ImageResponse, ModelResponse
from litellm.utils import post_call_processing


def completion():
    raise NotImplementedError


def image_generation():
    raise NotImplementedError


def responses():
    raise NotImplementedError


def test_post_call_processing_raises_on_empty_chat_completion_response():
    response = ModelResponse(
        model="gpt-4o-mini",
        choices=[{"message": {"content": "   "}}],
    )
    rules_obj = MagicMock()

    with pytest.raises(APIResponseValidationError, match="empty completion response"):
        post_call_processing(
            original_response=response,
            model="gpt-4o-mini",
            optional_params={},
            original_function=completion,
            rules_obj=rules_obj,
        )

    rules_obj.post_call_rules.assert_not_called()


def test_post_call_processing_raises_on_empty_image_generation_response():
    response = ImageResponse(data=[])
    rules_obj = MagicMock()

    with pytest.raises(
        APIResponseValidationError, match="empty image generation response"
    ):
        post_call_processing(
            original_response=response,
            model="gpt-image-1",
            optional_params={},
            original_function=image_generation,
            rules_obj=rules_obj,
        )

    rules_obj.post_call_rules.assert_not_called()


def test_post_call_processing_allows_image_generation_response_with_url():
    response = ImageResponse(data=[{"url": "https://example.com/image.png"}])
    rules_obj = MagicMock()

    post_call_processing(
        original_response=response,
        model="gpt-image-1",
        optional_params={},
        original_function=image_generation,
        rules_obj=rules_obj,
    )

    rules_obj.post_call_rules.assert_not_called()


def test_post_call_processing_raises_on_empty_responses_api_response():
    response = ResponsesAPIResponse(
        id="resp_123",
        created_at=1234567890,
        model="gpt-4o-mini",
        status="completed",
        output=[
            {
                "type": "message",
                "id": "msg_123",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "   "}],
            },
            {
                "type": "image_generation_call",
                "id": "img_123",
                "status": "completed",
                "result": None,
            },
        ],
    )
    rules_obj = MagicMock()

    with pytest.raises(
        APIResponseValidationError, match="empty responses api response"
    ):
        post_call_processing(
            original_response=response,
            model="gpt-4o-mini",
            optional_params={},
            original_function=responses,
            rules_obj=rules_obj,
        )

    rules_obj.post_call_rules.assert_not_called()


def test_post_call_processing_allows_responses_api_image_output():
    response = ResponsesAPIResponse(
        id="resp_123",
        created_at=1234567890,
        model="gpt-4o-mini",
        status="completed",
        output=[
            {
                "type": "image_generation_call",
                "id": "img_123",
                "status": "completed",
                "result": "base64-image-data",
            },
        ],
    )
    rules_obj = MagicMock()

    post_call_processing(
        original_response=response,
        model="gpt-4o-mini",
        optional_params={},
        original_function=responses,
        rules_obj=rules_obj,
    )

    rules_obj.post_call_rules.assert_not_called()


def test_post_call_processing_allows_tool_call_only_response():
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
    rules_obj = MagicMock()

    post_call_processing(
        original_response=response,
        model="gpt-4o-mini",
        optional_params={},
        original_function=completion,
        rules_obj=rules_obj,
    )

    rules_obj.post_call_rules.assert_not_called()
