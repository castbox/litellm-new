"""
DeerAPI Gemini 成本计算器
"""
from typing import Tuple

from litellm.litellm_core_utils.llm_cost_calc.utils import generic_cost_per_token
from litellm.types.utils import Usage


def cost_per_token(model: str, usage: Usage) -> Tuple[float, float]:
    """
    计算 DeerAPI Gemini 模型的 token 成本

    使用 custom_llm_provider="deerapi_gemini" 确保成本独立统计

    Args:
        model: 模型名称（不含供应商前缀）
        usage: LiteLLM Usage 对象

    Returns:
        Tuple[float, float] - (prompt_cost_usd, completion_cost_usd)
    """
    return generic_cost_per_token(
        model=model, usage=usage, custom_llm_provider="deerapi_gemini"
    )
