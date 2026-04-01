"""
Utility functions for ModelResponse and ModelResponseStream objects.
"""

from collections.abc import Sequence
from typing import Any, Optional

from litellm.exceptions import APIResponseValidationError
from litellm.types.utils import Delta, ModelResponseBase, ModelResponseStream

CHAT_COMPLETION_IMAGE_BLOCK_TYPES = {"image", "image_url", "input_image"}
CHAT_COMPLETION_TEXT_BLOCK_TYPES = {"input_text", "output_text", "text"}


def validate_first_chat_completion_response(
    model_response: Any,
    model: Optional[str],
    llm_provider: Optional[str] = None,
) -> None:
    """
    Validate that the first chat completion choice contains usable output.

    Raises:
        APIResponseValidationError: If the first choice is missing or empty.
    """
    if _first_chat_completion_choice_has_output(model_response):
        return

    raise APIResponseValidationError(
        message="empty completion response",
        llm_provider=llm_provider or "",
        model=model,
    )


def _first_chat_completion_choice_has_output(model_response: Any) -> bool:
    first_choice = _get_first_choice(model_response)
    if first_choice is None:
        return False

    message = getattr(first_choice, "message", None)
    if message is None:
        return False

    return _chat_completion_message_has_output(message)


def _get_first_choice(model_response: Any) -> Optional[Any]:
    choices = getattr(model_response, "choices", None)
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
        return None
    if len(choices) == 0:
        return None
    return choices[0]


def _chat_completion_message_has_output(message: Any) -> bool:
    content = getattr(message, "content", None)

    if _has_non_whitespace_text(content):
        return True

    if _content_blocks_have_output(content):
        return True

    images = getattr(message, "images", None)
    if _has_items(images):
        return True

    tool_calls = getattr(message, "tool_calls", None)
    if _has_items(tool_calls):
        return True

    return getattr(message, "function_call", None) is not None


def _content_blocks_have_output(content: Any) -> bool:
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
        return False

    for block in content:
        if _content_block_has_output(block):
            return True

    return False


def _content_block_has_output(block: Any) -> bool:
    if _has_non_whitespace_text(block):
        return True

    block_type = _get_field(block, "type")
    if block_type in CHAT_COMPLETION_IMAGE_BLOCK_TYPES:
        return True

    if block_type in CHAT_COMPLETION_TEXT_BLOCK_TYPES and _has_non_whitespace_text(
        _extract_text_value(_get_field(block, "text"))
    ):
        return True

    if _has_non_whitespace_text(_extract_text_value(_get_field(block, "text"))):
        return True

    return any(_get_field(block, field_name) is not None for field_name in ("image", "image_url"))


def _extract_text_value(text_value: Any) -> Optional[str]:
    if isinstance(text_value, str):
        return text_value

    if isinstance(text_value, dict):
        nested_text = text_value.get("text") or text_value.get("value")
        return nested_text if isinstance(nested_text, str) else None

    nested_text = getattr(text_value, "text", None)
    return nested_text if isinstance(nested_text, str) else None


def _get_field(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _has_non_whitespace_text(value: Any) -> bool:
    return isinstance(value, str) and len(value.strip()) > 0


def _has_items(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) > 0


def is_model_response_stream_empty(model_response: ModelResponseStream) -> bool:
    """
    Check if a ModelResponseStream is empty based on:
    - If finish_reason is set -> it's non empty
    - If any field in choices is set (e.g. content, tool calls, etc.) it's non empty
    - If usage exists -> it's non empty

    This function is robust and ignores fields that are always set (from ModelResponseBase)
    and checks for any meaningful content in other fields.

    Args:
        model_response: The ModelResponseStream to check

    Returns:
        bool: True if the stream is empty, False if it contains meaningful data
    """
    # Fields that are always set in ModelResponseBase and should be ignored
    # These are structural fields that don't indicate content
    BASE_FIELDS = ModelResponseBase.model_fields.keys()

    # Check if usage exists - this indicates meaningful data
    if getattr(model_response, "usage", None) is not None:
        return False

    # Check provider_specific_fields at the top level
    if (
        hasattr(model_response, "provider_specific_fields")
        and model_response.provider_specific_fields is not None
        and model_response.provider_specific_fields != {}
    ):
        return False

    # Check model_extra for dynamically added fields (this is where Pydantic stores them)
    if hasattr(model_response, "model_extra") and model_response.model_extra:
        for extra_field_name, extra_field_value in model_response.model_extra.items():
            if _has_meaningful_content(extra_field_value):
                return False

    # Check for any non-base fields that are set
    # Access model_fields on the class, not the instance, to avoid Pydantic 2.11+ deprecation warnings
    for model_response_field in type(model_response).model_fields.keys():
        # Skip base fields that are always set
        if model_response_field in BASE_FIELDS:
            continue

        # Skip choices - we'll handle them separately with deep inspection
        if model_response_field == "choices":
            continue

        # Check if any other field has meaningful content
        model_response_value = getattr(model_response, model_response_field, None)
        if _has_meaningful_content(model_response_value):
            return False

    # Deep check of choices for any meaningful content
    if hasattr(model_response, "choices") and model_response.choices:
        for choice in model_response.choices:
            if _is_choice_non_empty(choice):
                return False

    # If we get here, the stream is empty
    return True


def _has_meaningful_content(value: Any) -> bool:
    """
    Check if a value contains meaningful content.

    Args:
        value: The value to check

    Returns:
        bool: True if the value has meaningful content, False otherwise
    """
    if value is None:
        return False

    if isinstance(value, str):
        # Don't strip whitespace - preserve all content including newlines, spaces, etc.
        # Even pure whitespace characters like '\n' or ' ' are meaningful content
        return len(value) > 0

    if isinstance(value, (list, dict)):
        return len(value) > 0

    if isinstance(value, bool):
        return True  # Any boolean value is meaningful

    if isinstance(value, (int, float)):
        return True  # Any numeric value is meaningful

    # For other types (objects), consider them meaningful if they exist
    return True


def _is_choice_non_empty(choice: Any) -> bool:
    """
    Deep check if a choice contains any meaningful content.

    Args:
        choice: The choice object to check

    Returns:
        bool: True if the choice has meaningful content, False otherwise
    """
    # Check finish_reason
    if hasattr(choice, "finish_reason") and choice.finish_reason is not None:

        return True

    # Check logprobs
    if hasattr(choice, "logprobs") and choice.logprobs is not None:

        return True

    # Check enhancements (if present)
    if hasattr(choice, "enhancements") and choice.enhancements is not None:

        return True

    # Deep check delta object
    if hasattr(choice, "delta") and choice.delta is not None:
        if _is_delta_non_empty(choice.delta):

            return True

    # Check model_extra for dynamically added fields on the choice
    if hasattr(choice, "model_extra") and choice.model_extra:
        for extra_field_name, extra_field_value in choice.model_extra.items():
            # Skip certain structural fields that are just default/None placeholders
            if extra_field_name == "index" and extra_field_value == 0:

                continue
            if (
                extra_field_name in {"finish_reason", "logprobs"}
                and extra_field_value is None
            ):

                continue
            if extra_field_name == "delta":

                continue
            if _has_meaningful_content(extra_field_value):

                return True

    # Check for any other non-standard fields on the choice
    for attr_name in dir(choice):
        # Skip private attributes, methods, and known empty fields
        if (
            attr_name.startswith("_")
            or callable(getattr(choice, attr_name))
            or attr_name.startswith("model_")
            or attr_name
            in {
                "finish_reason",
                "index",
                "delta",
                "logprobs",
                "enhancements",
            }
        ):

            continue

        attr_value = getattr(choice, attr_name, None)
        if _has_meaningful_content(attr_value):

            return True

    return False


def _is_delta_non_empty(delta: Delta) -> bool:
    """
    Deep check if a delta object contains any meaningful content.

    Args:
        delta: The delta object to check

    Returns:
        bool: True if the delta has meaningful content, False otherwise
    """
    # Check model_extra for dynamically added fields (this is where Pydantic stores them)
    if hasattr(delta, "model_extra") and delta.model_extra:
        for extra_field_name, extra_field_value in delta.model_extra.items():
            # Even structural fields are meaningful if they have actual content
            if _has_meaningful_content(extra_field_value):

                return True

    # Check all regular attributes of the delta object
    for attr_name in dir(delta):
        # Skip private attributes, methods, and Pydantic-specific fields
        if (
            attr_name.startswith("_")
            or callable(getattr(delta, attr_name))
            or attr_name.startswith("model_")
        ):
            continue

        attr_value = getattr(delta, attr_name, None)
        if _has_meaningful_content(attr_value):

            return True

    return False
