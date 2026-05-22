import os
import sys
from unittest.mock import patch

sys.path.insert(
    0, os.path.abspath("../../..")
)  # Adds the parent directory to the system path

import litellm
import pytest
from litellm.litellm_core_utils.litellm_logging import Logging
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.utils import (
    Delta,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
    Usage,
)


class AsyncModelResponseIterator:
    def __init__(self, chunks):
        self.chunks = chunks
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.chunks):
            raise StopAsyncIteration
        chunk = self.chunks[self.index]
        self.index += 1
        return chunk


def _stream_chunk(content: str, usage=None) -> ModelResponseStream:
    return ModelResponseStream(
        id="chatcmpl-empty",
        object="chat.completion.chunk",
        created=1000000,
        model="gpt-4o",
        choices=[
            StreamingChoices(
                index=0,
                delta=Delta(role="assistant", content=content),
                finish_reason=None,
            )
        ],
        usage=usage,
    )


def _stream_logging_obj() -> Logging:
    logging_obj = Logging(
        model="primary-model",
        messages=[{"role": "user", "content": "Hello"}],
        stream=True,
        call_type="acompletion",
        start_time=0,
        litellm_call_id="12345",
        function_id="12345",
    )
    logging_obj.model_call_details["call_type"] = "acompletion"
    logging_obj.model_call_details["litellm_params"] = {}
    return logging_obj


def test_api_response_validation_error_skips_retries_when_fallbacks_exist():
    router = litellm.Router(
        model_list=[
            {
                "model_name": "primary-model",
                "litellm_params": {"model": "gpt-4o"},
            },
            {
                "model_name": "fallback-model",
                "litellm_params": {"model": "gpt-4o-mini"},
            },
        ],
        fallbacks=[{"primary-model": ["fallback-model"]}],
    )
    error = litellm.APIResponseValidationError(
        message="empty completion response",
        llm_provider="openai",
        model="gpt-4o",
    )

    try:
        router.should_retry_this_error(
            error=error,
            healthy_deployments=[{"model_name": "primary-model"}],
            all_deployments=[{"model_name": "primary-model"}],
            regular_fallbacks=[{"primary-model": ["fallback-model"]}],
        )
    except litellm.APIResponseValidationError as raised_error:
        assert raised_error is error
    else:
        raise AssertionError(
            "empty response validation errors should fallback immediately"
        )


def test_completion_falls_back_on_empty_non_streaming_response():
    router = litellm.Router(
        model_list=[
            {
                "model_name": "primary-model",
                "litellm_params": {
                    "model": "gpt-4o",
                    "mock_response": ModelResponse(
                        model="gpt-4o",
                        choices=[{"message": {"content": "   "}}],
                    ),
                },
            },
            {
                "model_name": "fallback-model",
                "litellm_params": {
                    "model": "gpt-4o-mini",
                    "mock_response": "fallback response",
                },
            },
        ],
        fallbacks=[{"primary-model": ["fallback-model"]}],
        set_verbose=True,
    )

    response = router.completion(
        model="primary-model",
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert response.choices[0].message.content == "fallback response"


@pytest.mark.asyncio
async def test_streaming_completion_falls_back_on_empty_success_response():
    router = litellm.Router(
        model_list=[
            {
                "model_name": "primary-model",
                "litellm_params": {"model": "gpt-4o", "api_key": "fake-key-1"},
            },
            {
                "model_name": "fallback-model",
                "litellm_params": {"model": "gpt-4o-mini", "api_key": "fake-key-2"},
            },
        ],
        fallbacks=[{"primary-model": ["fallback-model"]}],
    )
    empty_primary_stream = CustomStreamWrapper(
        completion_stream=AsyncModelResponseIterator(
            [
                _stream_chunk(
                    "",
                    usage=Usage(prompt_tokens=10, completion_tokens=0, total_tokens=10),
                )
            ]
        ),
        model="gpt-4o",
        logging_obj=_stream_logging_obj(),
        custom_llm_provider="openai",
    )
    fallback_stream = AsyncModelResponseIterator([_stream_chunk("fallback response")])

    with patch.object(
        router,
        "async_function_with_fallbacks_common_utils",
        return_value=fallback_stream,
    ) as mock_fallback:
        result = await router._acompletion_streaming_iterator(
            model_response=empty_primary_stream,
            messages=[{"role": "user", "content": "Hello"}],
            initial_kwargs={"model": "primary-model", "stream": True},
        )

        chunks = []
        async for chunk in result:
            chunks.append(chunk)

    assert mock_fallback.called
    assert [chunk.choices[0].delta.content for chunk in chunks] == [
        "fallback response"
    ]
    fallback_kwargs = mock_fallback.call_args.kwargs["kwargs"]
    assert fallback_kwargs["messages"] == [{"role": "user", "content": "Hello"}]
