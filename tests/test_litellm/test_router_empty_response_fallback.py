import os
import sys

sys.path.insert(
    0, os.path.abspath("../../..")
)  # Adds the parent directory to the system path

import litellm
from litellm.types.utils import ModelResponse


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
