from litellm.llms.openai.openai import OpenAIConfig
from litellm.secret_managers.main import get_secret_str


class AzureOpenAIV1Config(OpenAIConfig):
    @property
    def custom_llm_provider(self) -> str:
        return "azure_openai_v1"

    def get_openai_compatible_provider_info(
        self,
        api_base: str | None,
        api_key: str | None,
    ) -> tuple[str | None, str | None]:
        api_base = api_base or get_secret_str("AZURE_OPENAI_V1_API_BASE")
        dynamic_api_key = (
            api_key
            or get_secret_str("AZURE_OPENAI_V1_API_KEY")
            or get_secret_str("AZURE_OPENAI_API_KEY")
            or get_secret_str("AZURE_API_KEY")
        )
        return api_base, dynamic_api_key
