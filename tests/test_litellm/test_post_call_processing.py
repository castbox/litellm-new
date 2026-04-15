from unittest.mock import MagicMock

import pytest

from litellm.exceptions import APIResponseValidationError
from litellm.types.utils import ModelResponse
from litellm.utils import post_call_processing


def completion():
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
