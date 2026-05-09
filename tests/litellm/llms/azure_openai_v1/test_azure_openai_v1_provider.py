import litellm
from litellm.litellm_core_utils.get_llm_provider_logic import get_llm_provider
from litellm.llms.openai.openai import OpenAIConfig
from litellm.utils import ProviderConfigManager


AZURE_OPENAI_V1_BASE_URL = (
    "https://litellm-castbox-resource.services.ai.azure.com/openai/v1"
)


def test_azure_openai_v1_provider_resolution_with_custom_provider():
    model, provider, api_key, api_base = get_llm_provider(
        model="gpt-5.2",
        custom_llm_provider="azure_openai_v1",
        api_base=AZURE_OPENAI_V1_BASE_URL,
        api_key="azure-key",
    )

    assert model == "gpt-5.2"
    assert provider == "azure_openai_v1"
    assert api_key == "azure-key"
    assert api_base == AZURE_OPENAI_V1_BASE_URL


def test_azure_openai_v1_provider_resolution_with_model_prefix():
    model, provider, api_key, api_base = get_llm_provider(
        model="azure_openai_v1/gpt-5.2",
        api_base=AZURE_OPENAI_V1_BASE_URL,
        api_key="azure-key",
    )

    assert model == "gpt-5.2"
    assert provider == "azure_openai_v1"
    assert api_key == "azure-key"
    assert api_base == AZURE_OPENAI_V1_BASE_URL


def test_azure_openai_v1_uses_openai_config_for_gpt5_params():
    config = ProviderConfigManager.get_provider_chat_config(
        model="gpt-5.2",
        provider=litellm.LlmProviders.AZURE_OPENAI_V1,
    )

    assert isinstance(config, OpenAIConfig)
    optional_params = config.map_openai_params(
        non_default_params={"max_completion_tokens": 8},
        optional_params={},
        model="gpt-5.2",
        drop_params=False,
    )
    assert optional_params["max_completion_tokens"] == 8
    assert "max_tokens" not in optional_params
