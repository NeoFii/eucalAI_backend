"""Cost computation for API call billing (micro-yuan, 1 yuan = 1,000,000)."""

from __future__ import annotations

import math


def _calc(
    non_cached_input: int,
    completion_tokens: int,
    cached_tokens: int,
    input_price: int,
    output_price: int,
    cached_price: int,
) -> tuple[int, float, float, float]:
    input_cost = non_cached_input * input_price / 1_000_000
    output_cost = completion_tokens * output_price / 1_000_000
    cached_cost = cached_tokens * cached_price / 1_000_000
    total = input_cost + output_cost + cached_cost
    micro_yuan = math.ceil(total) if total > 0 else 0
    return micro_yuan, input_cost, output_cost, cached_cost


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    *,
    user_input_price: int,
    user_output_price: int,
    user_cached_price: int,
    provider_input_price: int,
    provider_output_price: int,
    provider_cached_price: int,
) -> tuple[int, int, dict]:
    """Return (user_cost_micro_yuan, provider_cost_micro_yuan, cost_detail)."""
    non_cached_input = max(prompt_tokens - cached_tokens, 0)

    user_cost, u_in, u_out, u_cached = _calc(
        non_cached_input, completion_tokens, cached_tokens,
        user_input_price, user_output_price, user_cached_price,
    )
    provider_cost, p_in, p_out, p_cached = _calc(
        non_cached_input, completion_tokens, cached_tokens,
        provider_input_price, provider_output_price, provider_cached_price,
    )

    cost_detail = {
        "non_cached_input_tokens": non_cached_input,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "user_prices": {
            "input": user_input_price,
            "output": user_output_price,
            "cached_input": user_cached_price,
        },
        "provider_prices": {
            "input": provider_input_price,
            "output": provider_output_price,
            "cached_input": provider_cached_price,
        },
        "user_cost": user_cost,
        "provider_cost": provider_cost,
    }
    return user_cost, provider_cost, cost_detail
