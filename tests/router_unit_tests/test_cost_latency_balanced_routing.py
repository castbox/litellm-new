import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import litellm
from litellm import Router
from litellm.router_strategy.cost_latency_balanced import (
    CostLatencyBalancedMetricsLogger,
    CostLatencyBalancedRouting,
    CostLatencyBalancedRoutingConfig,
)


def _build_router_and_strategy(
    **config_overrides,
):
    model_group = "balanced-group"
    router = Router(
        model_list=[
            {
                "model_name": model_group,
                "litellm_params": {
                    "model": "gpt-4o",
                    "rpm": 100,
                    "tpm": 2000,
                    "input_cost_per_token": 0.0002,
                    "output_cost_per_token": 0.0002,
                },
                "model_info": {"id": "d1"},
            },
            {
                "model_name": model_group,
                "litellm_params": {
                    "model": "gpt-4o-mini",
                    "rpm": 100,
                    "tpm": 2000,
                    "input_cost_per_token": 0.0001,
                    "output_cost_per_token": 0.0001,
                },
                "model_info": {"id": "d2"},
            },
        ],
        cooldown_time=30,
    )

    config = CostLatencyBalancedRoutingConfig(
        epsilon_explore=0.0,
        **config_overrides,
    )
    strategy = CostLatencyBalancedRouting(
        router=router,
        routing_config=config,
        random_seed=1337,
    )
    router.set_custom_routing_strategy(strategy)
    return router, strategy, model_group


def _get_active_metrics_loggers():
    return [
        callback
        for callback in litellm.callbacks
        if isinstance(callback, CostLatencyBalancedMetricsLogger)
    ]


def _set_strategy_state(
    router: Router,
    model_group: str,
    deployment_id: str,
    ttft_values: list,
    request_count_window: int,
    token_count_window: int,
    timeout_count_window: int = 0,
    five_xx_count_window: int = 0,
    window_seconds: int = 600,
    consecutive_abnormal_windows: int = 0,
):
    now = time.time()
    current_bucket = int(now // window_seconds)

    # keep samples/events inside strategy window
    ttft_samples = [[now - 5 + i * 0.01, float(v)] for i, v in enumerate(ttft_values)]
    request_events = [now - 1 for _ in range(request_count_window)]
    token_events = [
        [now - 1, float(token_count_window / max(1, request_count_window))]
        for _ in range(request_count_window)
    ]
    timeout_events = [now - 1 for _ in range(timeout_count_window)]
    five_xx_events = [now - 1 for _ in range(five_xx_count_window)]

    state = {
        "ttft_samples": ttft_samples,
        "ewma_ttft": float(sum(ttft_values) / max(1, len(ttft_values))),
        "request_events": request_events,
        "token_events": token_events,
        "timeout_events": timeout_events,
        "http_5xx_events": five_xx_events,
        "window_stats": {
            str(current_bucket): {
                "requests": request_count_window,
                "timeouts": timeout_count_window,
                "http_5xx": five_xx_count_window,
            }
        },
        "consecutive_abnormal_windows": consecutive_abnormal_windows,
    }

    key = CostLatencyBalancedMetricsLogger.get_deployment_cache_key(
        model_group=model_group,
        deployment_id=deployment_id,
    )
    router.cache.set_cache(key=key, value=state, ttl=3600)


def test_cost_latency_balanced_default_config_matches_unified_rollout_candidate():
    config = CostLatencyBalancedRoutingConfig()

    assert config.target_p95_ttft_seconds == 5.0
    assert config.slo_margin == 0.10
    assert config.max_timeout_rate_for_slo_pass == 0.02
    assert config.max_5xx_rate_for_slo_pass == 0.06
    assert config.weights_when_slo_met == (0.85, 0.05, 0.10)
    assert config.weights_when_slo_missed == (0.15, 0.75, 0.10)


def test_cost_latency_balanced_update_routing_config_refreshes_runtime_state():
    router, strategy, _ = _build_router_and_strategy()

    updated_config = strategy.update_routing_config(
        target_p95_ttft_seconds=4.0,
        slo_margin=0.15,
        window_seconds=120,
        weights_when_slo_met=(0.7, 0.2, 0.1),
        per_model_group_routing={"special-group": "cost-first"},
    )

    assert updated_config.target_p95_ttft_seconds == 4.0
    assert updated_config.slo_margin == 0.15
    assert updated_config.window_seconds == 120
    assert updated_config.weights_when_slo_met == (0.7, 0.2, 0.1)
    assert updated_config.per_model_group_routing == {"special-group": "cost-first"}
    assert strategy.weights_when_slo_met == pytest.approx((0.7, 0.2, 0.1))
    assert strategy.metrics_logger.routing_config.target_p95_ttft_seconds == 4.0
    assert strategy.metrics_logger.state_ttl == 3600


@pytest.mark.parametrize(
    "window_seconds,expected_ttl",
    [
        (300, 3600),
        (2000, 6000),
    ],
)
def test_cost_latency_balanced_replacing_strategy_object_replaces_metrics_logger(
    window_seconds: int, expected_ttl: int
):
    router, strategy, _ = _build_router_and_strategy()

    assert _get_active_metrics_loggers() == [strategy.metrics_logger]

    replacement_strategy = CostLatencyBalancedRouting(
        router=router,
        routing_config=CostLatencyBalancedRoutingConfig(
            epsilon_explore=0.0,
            window_seconds=window_seconds,
        ),
        random_seed=2026,
    )

    router.set_custom_routing_strategy(replacement_strategy)

    active_metrics_loggers = _get_active_metrics_loggers()
    assert active_metrics_loggers == [replacement_strategy.metrics_logger]
    assert active_metrics_loggers[0].state_ttl == expected_ttl


def test_cost_latency_balanced_router_discard_cleans_up_metrics_logger():
    router, strategy, _ = _build_router_and_strategy()

    assert _get_active_metrics_loggers() == [strategy.metrics_logger]

    router.discard()

    assert _get_active_metrics_loggers() == []


def test_cost_latency_balanced_per_model_group_cost_first_policy():
    model_group = "balanced-group"
    router, strategy, model_group = _build_router_and_strategy(
        per_model_group_routing={model_group: "cost-first"}
    )

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[1.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[9.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )

    request_kwargs = {"metadata": {}}
    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs=request_kwargs,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert selected["model_info"]["id"] == "d2"
    assert request_kwargs["metadata"]["_resolved_routing_mode"] == "cost-first"
    assert request_kwargs["metadata"]["_selected_reason"] == "lowest_cost_model_group_policy"
    assert request_kwargs["metadata"]["_slo_pass_set"] == []


def test_cost_latency_balanced_per_model_group_latency_first_policy():
    model_group = "balanced-group"
    router, strategy, model_group = _build_router_and_strategy(
        per_model_group_routing={model_group: "latency-first"}
    )

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[1.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[2.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )

    request_kwargs = {"metadata": {}}
    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs=request_kwargs,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert selected["model_info"]["id"] == "d1"
    assert request_kwargs["metadata"]["_resolved_routing_mode"] == "latency-first"
    assert (
        request_kwargs["metadata"]["_selected_reason"]
        == "lowest_latency_model_group_policy"
    )
    assert request_kwargs["metadata"]["_slo_pass_set"] == []


def test_cost_latency_balanced_prefers_lower_cost_within_slo():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[1.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[1.5] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )

    request_kwargs = {"metadata": {}}
    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs=request_kwargs,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert selected["model_info"]["id"] == "d2"
    assert sorted(request_kwargs["metadata"]["_slo_pass_set"]) == ["d1", "d2"]


def test_cost_latency_balanced_filters_out_over_slo_even_if_cheaper():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[4.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[2.8] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )

    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs={"metadata": {}},
        messages=[{"role": "user", "content": "hello"}],
    )
    assert selected["model_info"]["id"] == "d2"


def test_cost_latency_balanced_degraded_mode_prefers_latency():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[4.2] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[3.7] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )

    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs={"metadata": {}},
        messages=[{"role": "user", "content": "hello"}],
    )
    assert selected["model_info"]["id"] == "d2"


def test_cost_latency_balanced_reliability_gate_filters_high_5xx_within_slo():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[2.2] * 40,
        request_count_window=40,
        token_count_window=1000,
        five_xx_count_window=0,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[2.0] * 40,
        request_count_window=40,
        token_count_window=1000,
        five_xx_count_window=4,
        window_seconds=strategy.routing_config.window_seconds,
    )

    request_kwargs = {"metadata": {}}
    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs=request_kwargs,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert selected["model_info"]["id"] == "d1"
    assert request_kwargs["metadata"]["_slo_pass_set"] == ["d1"]


def test_cost_latency_balanced_load_penalty_suppresses_hot_deployment():
    router, strategy, model_group = _build_router_and_strategy()

    # equal latency / equal cost, but d1 has much higher load utilization
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[1.5] * 40,
        request_count_window=90,
        token_count_window=1500,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[1.5] * 40,
        request_count_window=10,
        token_count_window=100,
        window_seconds=strategy.routing_config.window_seconds,
    )

    # align custom costs for this test
    router.model_list[0]["litellm_params"]["input_cost_per_token"] = 0.0001
    router.model_list[0]["litellm_params"]["output_cost_per_token"] = 0.0001

    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs={"metadata": {}},
        messages=[{"role": "user", "content": "hello"}],
    )
    assert selected["model_info"]["id"] == "d2"


def test_cost_latency_balanced_cold_start_forced_exposure_every_20_requests():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[1.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[1.0] * 5,  # cold start
        request_count_window=5,
        token_count_window=200,
        window_seconds=strategy.routing_config.window_seconds,
    )

    request_counter_key = CostLatencyBalancedRouting.get_request_counter_key(model_group)
    router.cache.set_cache(key=request_counter_key, value=19, ttl=3600)

    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs={"metadata": {}},
        messages=[{"role": "user", "content": "hello"}],
    )
    assert selected["model_info"]["id"] == "d2"


def test_cost_latency_balanced_initializes_unseen_deployments_with_zero_ttft():
    router, _, model_group = _build_router_and_strategy()

    request_kwargs = {"metadata": {}}
    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs=request_kwargs,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert selected["model_info"]["id"] == "d2"
    assert request_kwargs["metadata"]["_selected_reason"] == "best_score_slo_missed"

    for deployment_id in ("d1", "d2"):
        cache_key = CostLatencyBalancedMetricsLogger.get_deployment_cache_key(
            model_group=model_group,
            deployment_id=deployment_id,
        )
        state = router.cache.get_cache(key=cache_key) or {}
        ttft_samples = state.get("ttft_samples", [])

        assert len(ttft_samples) == 1
        assert ttft_samples[0][1] == pytest.approx(0.0)
        assert state.get("ewma_ttft") == pytest.approx(0.0)
        assert state.get("request_events", []) == []
        assert state.get("token_events", []) == []


def test_cost_latency_balanced_cold_start_forced_exposure_when_slo_is_missed():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[6.0] * 40,
        request_count_window=10,
        token_count_window=1000,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[12.0] * 5,
        request_count_window=5,
        token_count_window=200,
        window_seconds=strategy.routing_config.window_seconds,
    )

    request_counter_key = CostLatencyBalancedRouting.get_request_counter_key(model_group)
    router.cache.set_cache(key=request_counter_key, value=19, ttl=3600)

    request_kwargs = {"metadata": {}}
    selected = router.get_available_deployment(
        model=model_group,
        request_kwargs=request_kwargs,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert selected["model_info"]["id"] == "d2"
    assert request_kwargs["metadata"]["_selected_reason"] == "cold_start_forced_exposure"
    assert request_kwargs["metadata"]["_slo_pass_set"] == []


def test_cost_latency_balanced_tie_break_uses_random_choice():
    router, strategy, model_group = _build_router_and_strategy()

    # identical stats/cost for tie path
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[1.2] * 40,
        request_count_window=10,
        token_count_window=100,
        window_seconds=strategy.routing_config.window_seconds,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[1.2] * 40,
        request_count_window=10,
        token_count_window=100,
        window_seconds=strategy.routing_config.window_seconds,
    )
    router.model_list[0]["litellm_params"]["input_cost_per_token"] = 0.0001
    router.model_list[0]["litellm_params"]["output_cost_per_token"] = 0.0001

    with patch.object(strategy._random, "choice", side_effect=lambda items: items[-1]):
        selected = router.get_available_deployment(
            model=model_group,
            request_kwargs={"metadata": {}},
            messages=[{"role": "user", "content": "hello"}],
        )

    assert selected["model_info"]["id"] == "d2"


def test_cost_latency_balanced_logger_cooldowns_after_three_abnormal_windows():
    router, strategy, model_group = _build_router_and_strategy(
        window_seconds=1,
        abnormal_timeout_rate_threshold=0.3,
        abnormal_5xx_rate_threshold=0.3,
        abnormal_consecutive_windows=3,
    )

    logger = strategy.metrics_logger
    failure_kwargs = {
        "litellm_params": {
            "metadata": {"model_group": model_group},
            "model_info": {"id": "d1"},
        },
        "exception": litellm.Timeout(
            message="timeout",
            model="gpt-4o",
            llm_provider="openai",
        ),
    }

    fake_now = [1000.0]

    def _fake_time():
        return fake_now[0]

    with patch(
        "litellm.router_strategy.cost_latency_balanced.time.time", _fake_time
    ), patch("litellm.caching.in_memory_cache.time.time", _fake_time):
        for i in range(3):
            fake_now[0] = 1000.0 + (i * 1.1)
            logger.log_failure_event(
                kwargs=failure_kwargs,
                response_obj=None,
                start_time=datetime.fromtimestamp(fake_now[0] - 0.5),
                end_time=datetime.fromtimestamp(fake_now[0]),
            )

        cooldowns = router.cooldown_cache.get_active_cooldowns(
            model_ids=["d1"],
            parent_otel_span=None,
        )
    assert len(cooldowns) == 1


def test_cost_latency_balanced_resets_state_after_cooldown_recovery():
    router, strategy, model_group = _build_router_and_strategy()

    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d1",
        ttft_values=[2.0] * 40,
        request_count_window=30,
        token_count_window=800,
        timeout_count_window=20,
        five_xx_count_window=10,
        window_seconds=strategy.routing_config.window_seconds,
        consecutive_abnormal_windows=3,
    )
    _set_strategy_state(
        router=router,
        model_group=model_group,
        deployment_id="d2",
        ttft_values=[1.0] * 40,
        request_count_window=10,
        token_count_window=200,
        window_seconds=strategy.routing_config.window_seconds,
    )

    # no active cooldown cache key -> should be treated as recovered and reset
    router.get_available_deployment(
        model=model_group,
        request_kwargs={"metadata": {}},
        messages=[{"role": "user", "content": "hello"}],
    )

    d1_key = CostLatencyBalancedMetricsLogger.get_deployment_cache_key(
        model_group=model_group,
        deployment_id="d1",
    )
    d1_state = router.cache.get_cache(key=d1_key) or {}
    assert d1_state.get("consecutive_abnormal_windows", 0) == 0
    ttft_samples = d1_state.get("ttft_samples", [])
    assert len(ttft_samples) == 1
    assert ttft_samples[0][1] == pytest.approx(0.0)
    assert d1_state.get("ewma_ttft") == pytest.approx(0.0)
