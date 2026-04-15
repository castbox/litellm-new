import os
import sys

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path

import litellm
from litellm import get_llm_provider
from litellm.litellm_core_utils.get_supported_openai_params import (
    get_supported_openai_params,
)


def test_deerapi_gemini_get_llm_provider():
    _, custom_llm_provider, _, _ = get_llm_provider("deerapi_gemini/gemini-2.0-flash")
    assert custom_llm_provider == "deerapi_gemini"


def test_ominilink_gemini_get_llm_provider():
    _, custom_llm_provider, _, _ = get_llm_provider(
        "ominilink_gemini/gemini-2.0-flash"
    )
    assert custom_llm_provider == "ominilink_gemini"


def test_toapis_get_llm_provider():
    _, custom_llm_provider, _, _ = get_llm_provider("toapis/gpt-4o-mini")
    assert custom_llm_provider == "toapis"


def test_custom_gemini_providers_match_google_ai_studio_supported_params():
    base_supported_params = litellm.GoogleAIStudioGeminiConfig().get_supported_openai_params(
        model="gemini-2.0-flash"
    )

    deerapi_supported_params = get_supported_openai_params(
        model="gemini-2.0-flash", custom_llm_provider="deerapi_gemini"
    )
    ominilink_supported_params = get_supported_openai_params(
        model="gemini-2.0-flash", custom_llm_provider="ominilink_gemini"
    )

    assert deerapi_supported_params == base_supported_params
    assert ominilink_supported_params == base_supported_params


def test_toapis_supported_openai_params_match_provider_config():
    expected_supported_params = litellm.ToAPIsChatConfig().get_supported_openai_params(
        model="gpt-4o-mini"
    )
    supported_params = get_supported_openai_params(
        model="gpt-4o-mini", custom_llm_provider="toapis"
    )

    assert supported_params == expected_supported_params
