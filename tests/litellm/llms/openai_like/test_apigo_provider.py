"""
Unit tests for the ApiGo OpenAI-compatible provider.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
)

from litellm.llms.openai_like.dynamic_config import (
    create_config_class,
    create_responses_config_class,
)
from litellm.llms.openai_like.json_loader import JSONProviderRegistry
from litellm.types.router import GenericLiteLLMParams

APIGO_BASE_URL = "https://vip.apigo.ai/v1"
REPO_ROOT = Path(__file__).resolve().parents[4]


def _get_config():
    provider = JSONProviderRegistry.get("apigo")
    assert provider is not None
    config_class = create_config_class(provider)
    return config_class()


def test_apigo_provider_registered():
    provider = JSONProviderRegistry.get("apigo")
    assert provider is not None
    assert provider.base_url == APIGO_BASE_URL
    assert provider.api_key_env == "APIGO_API_KEY"
    assert provider.api_base_env == "APIGO_API_BASE"
    assert provider.supported_endpoints == ["/v1/chat/completions", "/v1/responses"]


def test_apigo_resolves_env_api_key(monkeypatch):
    config = _get_config()
    monkeypatch.setenv("APIGO_API_KEY", "test-key")
    api_base, api_key = config._get_openai_compatible_provider_info(None, None)
    assert api_base == APIGO_BASE_URL
    assert api_key == "test-key"


def test_apigo_complete_url_appends_endpoint():
    config = _get_config()
    url = config.get_complete_url(
        api_base=APIGO_BASE_URL,
        api_key="test-key",
        model="apigo/gpt-4o",
        optional_params={},
        litellm_params={},
        stream=False,
    )
    assert url == f"{APIGO_BASE_URL}/chat/completions"


def test_apigo_provider_resolution():
    from litellm.litellm_core_utils.get_llm_provider_logic import get_llm_provider

    model, provider, api_key, api_base = get_llm_provider(
        model="apigo/gpt-4o",
        custom_llm_provider=None,
        api_base=None,
        api_key=None,
    )

    assert model == "gpt-4o"
    assert provider == "apigo"
    assert api_base == APIGO_BASE_URL


def test_apigo_responses_config():
    provider = JSONProviderRegistry.get("apigo")
    assert provider is not None
    assert JSONProviderRegistry.supports_responses_api("apigo") is True

    config_class = create_responses_config_class(provider)
    config = config_class()
    headers = config.validate_environment(
        headers={},
        model="gpt-4o",
        litellm_params=GenericLiteLLMParams(api_key="test-key"),
    )

    assert config.custom_llm_provider == "apigo"
    assert config.get_complete_url(api_base=None, litellm_params={}) == (
        f"{APIGO_BASE_URL}/responses"
    )
    assert headers["Authorization"] == "Bearer test-key"


def test_apigo_provider_config_manager():
    from litellm import LlmProviders
    from litellm.utils import ProviderConfigManager

    config = ProviderConfigManager.get_provider_chat_config(
        model="gpt-4o", provider=LlmProviders.APIGO
    )

    assert config is not None
    assert config.custom_llm_provider == "apigo"


def test_apigo_dashboard_provider_fields_present():
    provider_fields_path = (
        REPO_ROOT / "litellm" / "proxy" / "public_endpoints" / "provider_create_fields.json"
    )
    provider_fields = json.loads(provider_fields_path.read_text())
    apigo = next((p for p in provider_fields if p["litellm_provider"] == "apigo"), None)

    assert apigo is not None
    assert apigo["provider"] == "ApiGo"
    assert apigo["provider_display_name"] == "ApiGo"
    assert apigo["default_model_placeholder"] == "gpt-4o"

    field_by_key = {field["key"]: field for field in apigo["credential_fields"]}
    assert field_by_key["api_base"]["default_value"] == APIGO_BASE_URL
    assert field_by_key["api_key"]["required"] is True
