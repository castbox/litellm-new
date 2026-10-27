import pytest

import litellm
from litellm.types.utils import Usage


@pytest.mark.parametrize("provider", ("deerapi_gemini", "ominilink_gemini"))
def test_custom_gemini_uses_its_own_registered_prices_and_cached_usage(provider, monkeypatch):
    monkeypatch.setattr(litellm, "model_cost", dict(litellm.model_cost))
    litellm.register_model(
        {
            f"{provider}/unit-pricing-model": {
                "litellm_provider": provider,
                "mode": "chat",
                "input_cost_per_token": 0.01,
                "output_cost_per_token": 0.03,
                "cache_read_input_token_cost": 0.004,
            }
        }
    )

    costs = litellm.cost_per_token(
        model="unit-pricing-model",
        custom_llm_provider=provider,
        usage_object=Usage(prompt_tokens=100, completion_tokens=20, prompt_tokens_details={"cached_tokens": 40}),
    )

    assert costs == pytest.approx((60 * 0.01 + 40 * 0.004, 20 * 0.03))
