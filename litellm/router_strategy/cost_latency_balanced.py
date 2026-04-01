"""
SLO-first custom routing strategy that balances cost + latency.

This strategy is designed to be used with:
    router.set_custom_routing_strategy(CostLatencyBalancedRouting(router=router))

It keeps strategy-local rolling stats in router cache under:
    cost_latency_balanced:{model_group}:{deployment_id}
"""

import math
import random
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Union, cast

import litellm
from litellm import token_counter
from litellm.caching.caching import DualCache
from litellm.integrations.custom_logger import CustomLogger
from litellm.litellm_core_utils.core_helpers import _get_parent_otel_span_from_kwargs
from litellm.router_utils.cooldown_cache import CooldownCache
from litellm.router_utils.cooldown_handlers import _get_cooldown_deployments
from litellm.router_utils.handle_error import async_raise_no_deployment_exception
from litellm.types.router import CustomRoutingStrategyBase, RouterRateLimitError
from litellm.types.utils import LiteLLMPydanticObjectBase, ModelResponse
from pydantic import Field

if TYPE_CHECKING:
    from litellm.router import Router


ModelGroupRoutingMode = Literal["balanced", "cost-first", "latency-first"]


class CostLatencyBalancedRoutingConfig(LiteLLMPydanticObjectBase):
    # Phase 1 unified rollout defaults.
    target_p95_ttft_seconds: float = 5.0
    slo_margin: float = 0.10
    window_seconds: int = 600
    min_samples_for_strict_slo: int = 30
    max_timeout_rate_for_slo_pass: Optional[float] = 0.02
    max_5xx_rate_for_slo_pass: Optional[float] = 0.06
    epsilon_explore: float = 0.05
    # (cost, latency, load)
    weights_when_slo_met: Tuple[float, float, float] = (0.85, 0.05, 0.10)
    weights_when_slo_missed: Tuple[float, float, float] = (0.15, 0.75, 0.10)
    failure_penalty_timeout: float = 0.5
    failure_penalty_5xx: float = 0.3
    ewma_alpha: float = 0.2
    cold_start_exposure_interval: int = 20
    max_explore_cost_multiplier: float = 1.2
    abnormal_timeout_rate_threshold: float = 0.3
    abnormal_5xx_rate_threshold: float = 0.3
    abnormal_consecutive_windows: int = 3
    default_routing_mode: ModelGroupRoutingMode = "balanced"
    per_model_group_routing: Dict[str, ModelGroupRoutingMode] = Field(
        default_factory=dict
    )


class CostLatencyBalancedMetricsLogger(CustomLogger):
    """
    Custom logger that stores rolling per-deployment metrics required by
    CostLatencyBalancedRouting.
    """

    CACHE_PREFIX = "cost_latency_balanced"

    def __init__(
        self,
        router_cache: DualCache,
        routing_config: CostLatencyBalancedRoutingConfig,
        router: Optional["Router"] = None,
    ):
        self.router_cache = router_cache
        self.routing_config = routing_config
        self.router = router
        self.state_ttl = max(3600, int(self.routing_config.window_seconds * 3))

    @staticmethod
    def get_deployment_cache_key(model_group: str, deployment_id: str) -> str:
        return (
            f"{CostLatencyBalancedMetricsLogger.CACHE_PREFIX}:"
            f"{model_group}:{deployment_id}"
        )

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._update_metrics(
            kwargs=kwargs,
            response_obj=response_obj,
            start_time=start_time,
            end_time=end_time,
            is_failure=False,
        )

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        await self._async_update_metrics(
            kwargs=kwargs,
            response_obj=response_obj,
            start_time=start_time,
            end_time=end_time,
            is_failure=False,
        )

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._update_metrics(
            kwargs=kwargs,
            response_obj=response_obj,
            start_time=start_time,
            end_time=end_time,
            is_failure=True,
        )

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        await self._async_update_metrics(
            kwargs=kwargs,
            response_obj=response_obj,
            start_time=start_time,
            end_time=end_time,
            is_failure=True,
        )

    def _update_metrics(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Union[datetime, float],
        end_time: Union[datetime, float],
        is_failure: bool,
    ) -> None:
        model_group, deployment_id = self._extract_model_group_and_id(kwargs)
        if model_group is None or deployment_id is None:
            return

        cache_key = self.get_deployment_cache_key(
            model_group=model_group,
            deployment_id=deployment_id,
        )
        state = self.router_cache.get_cache(key=cache_key) or {}
        state = cast(Dict[str, Any], state)
        now = time.time()

        failure_type, status_code = self._classify_failure(kwargs.get("exception"))

        updated_state = self._apply_event_to_state(
            state=state,
            now=now,
            start_time=start_time,
            end_time=end_time,
            completion_start_time=kwargs.get("completion_start_time"),
            response_obj=response_obj,
            failure_type=failure_type if is_failure else None,
        )

        if is_failure:
            self._maybe_put_deployment_on_cooldown(
                model_id=deployment_id,
                state=updated_state,
                now=now,
                failure_type=failure_type,
                status_code=status_code,
                original_exception=kwargs.get("exception"),
            )

        self.router_cache.set_cache(
            key=cache_key,
            value=updated_state,
            ttl=self.state_ttl,
        )

    async def _async_update_metrics(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Union[datetime, float],
        end_time: Union[datetime, float],
        is_failure: bool,
    ) -> None:
        model_group, deployment_id = self._extract_model_group_and_id(kwargs)
        if model_group is None or deployment_id is None:
            return

        cache_key = self.get_deployment_cache_key(
            model_group=model_group,
            deployment_id=deployment_id,
        )
        state = await self.router_cache.async_get_cache(key=cache_key) or {}
        state = cast(Dict[str, Any], state)
        now = time.time()

        failure_type, status_code = self._classify_failure(kwargs.get("exception"))

        updated_state = self._apply_event_to_state(
            state=state,
            now=now,
            start_time=start_time,
            end_time=end_time,
            completion_start_time=kwargs.get("completion_start_time"),
            response_obj=response_obj,
            failure_type=failure_type if is_failure else None,
        )

        if is_failure:
            self._maybe_put_deployment_on_cooldown(
                model_id=deployment_id,
                state=updated_state,
                now=now,
                failure_type=failure_type,
                status_code=status_code,
                original_exception=kwargs.get("exception"),
            )

        await self.router_cache.async_set_cache(
            key=cache_key,
            value=updated_state,
            ttl=self.state_ttl,
        )

    def _apply_event_to_state(
        self,
        state: Dict[str, Any],
        now: float,
        start_time: Union[datetime, float],
        end_time: Union[datetime, float],
        completion_start_time: Optional[Union[datetime, float]],
        response_obj: Any,
        failure_type: Optional[str],
    ) -> Dict[str, Any]:
        state.setdefault("ttft_samples", [])
        state.setdefault("request_events", [])
        state.setdefault("token_events", [])
        state.setdefault("timeout_events", [])
        state.setdefault("http_5xx_events", [])
        state.setdefault("window_stats", {})
        state.setdefault("ewma_ttft", None)
        state.setdefault("last_cooldown_bucket", None)

        ttft_seconds = self._compute_ttft_seconds(
            start_time=start_time,
            end_time=end_time,
            completion_start_time=completion_start_time,
        )
        total_tokens = self._extract_total_tokens(response_obj=response_obj)

        state["request_events"].append(now)
        state["token_events"].append([now, total_tokens])
        state["ttft_samples"].append([now, ttft_seconds])

        current_ewma = state.get("ewma_ttft")
        alpha = self.routing_config.ewma_alpha
        if isinstance(current_ewma, (int, float)):
            state["ewma_ttft"] = alpha * ttft_seconds + (1 - alpha) * float(current_ewma)
        else:
            state["ewma_ttft"] = ttft_seconds

        current_bucket = int(now // self.routing_config.window_seconds)
        bucket_stats = state["window_stats"].setdefault(
            str(current_bucket),
            {
                "requests": 0,
                "timeouts": 0,
                "http_5xx": 0,
            },
        )
        bucket_stats["requests"] = int(bucket_stats.get("requests", 0)) + 1

        if failure_type == "timeout":
            state["timeout_events"].append(now)
            bucket_stats["timeouts"] = int(bucket_stats.get("timeouts", 0)) + 1
        elif failure_type == "http_5xx":
            state["http_5xx_events"].append(now)
            bucket_stats["http_5xx"] = int(bucket_stats.get("http_5xx", 0)) + 1

        self._prune_state_in_place(
            state=state,
            now=now,
            window_seconds=self.routing_config.window_seconds,
            buckets_to_keep=self.routing_config.abnormal_consecutive_windows + 3,
        )

        state["consecutive_abnormal_windows"] = self._get_consecutive_abnormal_windows(
            state=state,
            current_bucket=current_bucket,
        )
        return state

    def _maybe_put_deployment_on_cooldown(
        self,
        model_id: str,
        state: Dict[str, Any],
        now: float,
        failure_type: Optional[str],
        status_code: Optional[int],
        original_exception: Optional[Exception],
    ) -> None:
        if self.router is None:
            return
        if failure_type not in {"timeout", "http_5xx"}:
            return

        current_bucket = int(now // self.routing_config.window_seconds)
        last_cooldown_bucket = state.get("last_cooldown_bucket")
        consecutive_windows = int(state.get("consecutive_abnormal_windows", 0))

        if (
            consecutive_windows < self.routing_config.abnormal_consecutive_windows
            or last_cooldown_bucket == current_bucket
        ):
            return

        cooldown_exception: Exception
        if isinstance(original_exception, Exception):
            cooldown_exception = original_exception
        else:
            cooldown_exception = Exception(
                "deployment exceeded abnormal timeout/5xx window threshold"
            )

        exception_status = status_code or (408 if failure_type == "timeout" else 500)
        self.router.cooldown_cache.add_deployment_to_cooldown(
            model_id=model_id,
            original_exception=cooldown_exception,
            exception_status=exception_status,
            cooldown_time=None,
        )
        state["last_cooldown_bucket"] = current_bucket

    def _extract_model_group_and_id(
        self, model_call_kwargs: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        litellm_params = model_call_kwargs.get("litellm_params", {})
        if not isinstance(litellm_params, dict):
            return None, None

        metadata_field = self._select_metadata_field(litellm_params)
        metadata = litellm_params.get(metadata_field or "metadata", {}) or {}
        model_group = metadata.get("model_group")

        deployment_id = litellm_params.get("model_info", {}).get("id")
        if deployment_id is None or model_group is None:
            return None, None
        if isinstance(deployment_id, int):
            deployment_id = str(deployment_id)
        return str(model_group), str(deployment_id)

    def _classify_failure(
        self, exception: Any
    ) -> Tuple[Optional[str], Optional[int]]:
        if exception is None:
            return None, None

        if isinstance(exception, litellm.Timeout) or "timeout" in str(
            type(exception).__name__
        ).lower():
            return "timeout", 408

        status_code = self._extract_status_code(exception)
        if status_code is not None and 500 <= status_code < 600:
            return "http_5xx", status_code

        return None, status_code

    @staticmethod
    def _extract_status_code(exception: Any) -> Optional[int]:
        status_code = getattr(exception, "status_code", None)
        if isinstance(status_code, str) and status_code.isdigit():
            return int(status_code)
        if isinstance(status_code, int):
            return status_code

        response = getattr(exception, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    def _get_consecutive_abnormal_windows(
        self, state: Dict[str, Any], current_bucket: int
    ) -> int:
        streak = 0
        window_stats = state.get("window_stats", {}) or {}
        max_lookback = max(
            self.routing_config.abnormal_consecutive_windows + 2,
            5,
        )
        for bucket in range(current_bucket, current_bucket - max_lookback, -1):
            stats = window_stats.get(str(bucket))
            if not isinstance(stats, dict):
                break
            request_count = int(stats.get("requests", 0))
            if request_count <= 0:
                break

            timeout_rate = float(stats.get("timeouts", 0)) / request_count
            five_xx_rate = float(stats.get("http_5xx", 0)) / request_count
            if (
                timeout_rate >= self.routing_config.abnormal_timeout_rate_threshold
                or five_xx_rate >= self.routing_config.abnormal_5xx_rate_threshold
            ):
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _extract_total_tokens(response_obj: Any) -> int:
        try:
            if isinstance(response_obj, ModelResponse):
                usage = getattr(response_obj, "usage", None)
            else:
                usage = getattr(response_obj, "usage", None)

            total_tokens = getattr(usage, "total_tokens", 0) if usage is not None else 0
            if isinstance(total_tokens, int):
                return total_tokens
            if isinstance(total_tokens, float):
                return int(total_tokens)
        except Exception:
            pass
        return 0

    @staticmethod
    def _compute_ttft_seconds(
        start_time: Union[datetime, float],
        end_time: Union[datetime, float],
        completion_start_time: Optional[Union[datetime, float]],
    ) -> float:
        start_ts = CostLatencyBalancedMetricsLogger._to_timestamp(start_time)
        first_token_ts = CostLatencyBalancedMetricsLogger._to_timestamp(
            completion_start_time if completion_start_time is not None else end_time
        )
        ttft_seconds = max(0.0, first_token_ts - start_ts)
        return float(ttft_seconds)

    @staticmethod
    def _to_timestamp(value: Union[datetime, float, int, None]) -> float:
        if isinstance(value, datetime):
            return value.timestamp()
        if isinstance(value, (float, int)):
            return float(value)
        return time.time()

    @staticmethod
    def _prune_state_in_place(
        state: Dict[str, Any],
        now: float,
        window_seconds: int,
        buckets_to_keep: int,
    ) -> None:
        cutoff_ts = now - window_seconds

        def _filter_ts_events(values: Any) -> List[float]:
            if not isinstance(values, list):
                return []
            return [float(v) for v in values if isinstance(v, (int, float)) and v >= cutoff_ts]

        def _filter_token_events(values: Any) -> List[List[float]]:
            if not isinstance(values, list):
                return []
            filtered: List[List[float]] = []
            for item in values:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                ts, tokens = item
                if isinstance(ts, (int, float)) and float(ts) >= cutoff_ts:
                    filtered.append([float(ts), float(tokens) if isinstance(tokens, (int, float)) else 0.0])
            return filtered

        state["request_events"] = _filter_ts_events(state.get("request_events"))
        state["timeout_events"] = _filter_ts_events(state.get("timeout_events"))
        state["http_5xx_events"] = _filter_ts_events(state.get("http_5xx_events"))
        state["token_events"] = _filter_token_events(state.get("token_events"))

        ttft_samples = state.get("ttft_samples")
        if isinstance(ttft_samples, list):
            filtered_ttft: List[List[float]] = []
            for item in ttft_samples:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                ts, value = item
                if (
                    isinstance(ts, (int, float))
                    and isinstance(value, (int, float))
                    and float(ts) >= cutoff_ts
                ):
                    filtered_ttft.append([float(ts), float(value)])
            state["ttft_samples"] = filtered_ttft
        else:
            state["ttft_samples"] = []

        current_bucket = int(now // window_seconds)
        oldest_bucket = current_bucket - max(1, buckets_to_keep)
        window_stats = state.get("window_stats", {})
        if isinstance(window_stats, dict):
            for bucket_key in list(window_stats.keys()):
                try:
                    if int(bucket_key) < oldest_bucket:
                        window_stats.pop(bucket_key, None)
                except ValueError:
                    window_stats.pop(bucket_key, None)
        else:
            state["window_stats"] = {}


class CostLatencyBalancedRouting(CustomRoutingStrategyBase):
    """
    SLO-first custom routing strategy:
    1) Filter by SLO p95 TTFT threshold when possible.
    2) Score by (cost, latency, load) + failure penalty.
    3) Add bounded exploration and cold-start exposure.
    """

    REQUEST_COUNTER_PREFIX = "cost_latency_balanced:request_counter"

    def __init__(
        self,
        router: "Router",
        routing_config: Optional[Union[CostLatencyBalancedRoutingConfig, Dict[str, Any]]] = None,
        random_seed: Optional[int] = None,
    ):
        self.router = router
        self._random = random.Random(random_seed)
        self._set_routing_config(routing_config=routing_config)

        self.metrics_logger = CostLatencyBalancedMetricsLogger(
            router_cache=self.router.cache,
            routing_config=self.routing_config,
            router=self.router,
        )

    def on_attach(self, router: "Router") -> None:
        self.router = router
        self.metrics_logger.router = router
        if isinstance(litellm.callbacks, list):
            litellm.logging_callback_manager.add_litellm_callback(self.metrics_logger)  # type: ignore[arg-type]

    def cleanup(self) -> None:
        if isinstance(litellm.callbacks, list):
            litellm.logging_callback_manager.remove_callback_from_list_by_object(
                litellm.callbacks, self.metrics_logger, require_self=False
            )

    def update_routing_config(
        self,
        routing_config: Optional[
            Union[CostLatencyBalancedRoutingConfig, Dict[str, Any]]
        ] = None,
        **config_overrides: Any,
    ) -> CostLatencyBalancedRoutingConfig:
        """
        Update routing config at runtime without reinstalling the strategy object.

        This keeps existing rolling metrics in cache and refreshes the strategy's
        scoring weights and logger TTL immediately.
        """

        if routing_config is None:
            config_payload = self._routing_config_to_dict(self.routing_config)
        elif isinstance(routing_config, CostLatencyBalancedRoutingConfig):
            config_payload = self._routing_config_to_dict(routing_config)
        else:
            config_payload = dict(routing_config)

        config_payload.update(config_overrides)
        self._set_routing_config(
            routing_config=CostLatencyBalancedRoutingConfig(**config_payload)
        )
        return self.routing_config

    def _set_routing_config(
        self,
        routing_config: Optional[
            Union[CostLatencyBalancedRoutingConfig, Dict[str, Any]]
        ],
    ) -> None:
        if routing_config is None:
            resolved_config = CostLatencyBalancedRoutingConfig()
        elif isinstance(routing_config, CostLatencyBalancedRoutingConfig):
            resolved_config = routing_config
        else:
            resolved_config = CostLatencyBalancedRoutingConfig(**routing_config)

        self.routing_config = resolved_config
        self.weights_when_slo_met = self._normalize_weights(
            self.routing_config.weights_when_slo_met
        )
        self.weights_when_slo_missed = self._normalize_weights(
            self.routing_config.weights_when_slo_missed
        )
        if hasattr(self, "metrics_logger"):
            self.metrics_logger.routing_config = self.routing_config
            self.metrics_logger.state_ttl = max(
                3600, int(self.routing_config.window_seconds * 3)
            )

    @staticmethod
    def _routing_config_to_dict(
        routing_config: CostLatencyBalancedRoutingConfig,
    ) -> Dict[str, Any]:
        if hasattr(routing_config, "model_dump"):
            return cast(Dict[str, Any], routing_config.model_dump())
        return cast(Dict[str, Any], routing_config.dict())

    @staticmethod
    def get_request_counter_key(model_group: str) -> str:
        return f"{CostLatencyBalancedRouting.REQUEST_COUNTER_PREFIX}:{model_group}"

    async def async_get_available_deployment(
        self,
        model: str,
        messages: Optional[List[Dict[str, str]]] = None,
        input: Optional[Union[str, List]] = None,
        specific_deployment: Optional[bool] = False,
        request_kwargs: Optional[Dict] = None,
    ):
        request_kwargs = request_kwargs or {}
        parent_otel_span = _get_parent_otel_span_from_kwargs(request_kwargs)

        pre_routing_hook_response = await self.router.async_pre_routing_hook(
            model=model,
            request_kwargs=request_kwargs,
            messages=messages,
            input=input,
            specific_deployment=specific_deployment,
        )
        if pre_routing_hook_response is not None:
            model = pre_routing_hook_response.model
            messages = pre_routing_hook_response.messages

        healthy_deployments = await self.router.async_get_healthy_deployments(
            model=model,
            request_kwargs=request_kwargs,
            messages=messages,
            input=input,
            specific_deployment=specific_deployment,
            parent_otel_span=parent_otel_span,
        )
        if isinstance(healthy_deployments, dict):
            return healthy_deployments

        request_counter = await self.router.cache.async_increment_cache(
            key=self.get_request_counter_key(model_group=model),
            value=1,
            ttl=max(3600, self.routing_config.window_seconds * 3),
        )

        selected_deployment = await self._async_select_deployment(
            model_group=model,
            healthy_deployments=healthy_deployments,
            messages=messages,
            input=input,
            request_kwargs=request_kwargs,
            request_counter=request_counter,
        )
        if selected_deployment is None:
            exception = await async_raise_no_deployment_exception(
                litellm_router_instance=self.router,
                model=model,
                parent_otel_span=parent_otel_span,
            )
            raise exception
        return selected_deployment

    def get_available_deployment(
        self,
        model: str,
        messages: Optional[List[Dict[str, str]]] = None,
        input: Optional[Union[str, List]] = None,
        specific_deployment: Optional[bool] = False,
        request_kwargs: Optional[Dict] = None,
    ):
        model, healthy_deployments = self.router._common_checks_available_deployment(
            model=model,
            messages=messages,
            input=input,
            specific_deployment=specific_deployment,
            request_kwargs=request_kwargs,
        )

        if isinstance(healthy_deployments, dict):
            return healthy_deployments

        parent_otel_span = _get_parent_otel_span_from_kwargs(request_kwargs)
        cooldown_deployments = _get_cooldown_deployments(
            litellm_router_instance=self.router,
            parent_otel_span=parent_otel_span,
        )
        healthy_deployments = self.router._filter_cooldown_deployments(
            healthy_deployments=healthy_deployments,
            cooldown_deployments=cooldown_deployments,
        )

        if self.router.enable_pre_call_checks and messages is not None:
            healthy_deployments = self.router._pre_call_checks(
                model=model,
                healthy_deployments=healthy_deployments,
                messages=messages,
                request_kwargs=request_kwargs,
            )

        if len(healthy_deployments) == 0:
            model_ids = self.router.get_model_ids(model_name=model)
            cooldown_time = self.router.cooldown_cache.get_min_cooldown(
                model_ids=model_ids,
                parent_otel_span=parent_otel_span,
            )
            cooldown_list = _get_cooldown_deployments(
                litellm_router_instance=self.router,
                parent_otel_span=parent_otel_span,
            )
            raise RouterRateLimitError(
                model=model,
                cooldown_time=cooldown_time,
                enable_pre_call_checks=self.router.enable_pre_call_checks,
                cooldown_list=cooldown_list,
            )

        request_counter = self.router.cache.increment_cache(
            key=self.get_request_counter_key(model_group=model),
            value=1,
            ttl=max(3600, self.routing_config.window_seconds * 3),
        )

        selected_deployment = self._select_deployment(
            model_group=model,
            healthy_deployments=healthy_deployments,
            messages=messages,
            input=input,
            request_kwargs=request_kwargs,
            request_counter=request_counter,
        )
        if selected_deployment is None:
            model_ids = self.router.get_model_ids(model_name=model)
            cooldown_time = self.router.cooldown_cache.get_min_cooldown(
                model_ids=model_ids,
                parent_otel_span=parent_otel_span,
            )
            cooldown_list = _get_cooldown_deployments(
                litellm_router_instance=self.router,
                parent_otel_span=parent_otel_span,
            )
            raise RouterRateLimitError(
                model=model,
                cooldown_time=cooldown_time,
                enable_pre_call_checks=self.router.enable_pre_call_checks,
                cooldown_list=cooldown_list,
            )
        return selected_deployment

    async def _async_select_deployment(
        self,
        model_group: str,
        healthy_deployments: List[Dict[str, Any]],
        messages: Optional[List[Dict[str, str]]],
        input: Optional[Union[str, List]],
        request_kwargs: Optional[Dict[str, Any]],
        request_counter: float,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        deployment_state_map: Dict[str, Dict[str, Any]] = {}
        for deployment in healthy_deployments:
            model_id = self._get_model_id(deployment)
            if model_id is None:
                continue
            cache_key = CostLatencyBalancedMetricsLogger.get_deployment_cache_key(
                model_group=model_group,
                deployment_id=model_id,
            )
            state = await self.router.cache.async_get_cache(key=cache_key) or {}
            deployment_state_map[model_id] = cast(Dict[str, Any], state)

        return self._select_from_states(
            model_group=model_group,
            healthy_deployments=healthy_deployments,
            deployment_state_map=deployment_state_map,
            now=now,
            messages=messages,
            input=input,
            request_kwargs=request_kwargs,
            request_counter=request_counter,
        )

    def _select_deployment(
        self,
        model_group: str,
        healthy_deployments: List[Dict[str, Any]],
        messages: Optional[List[Dict[str, str]]],
        input: Optional[Union[str, List]],
        request_kwargs: Optional[Dict[str, Any]],
        request_counter: float,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        deployment_state_map: Dict[str, Dict[str, Any]] = {}
        for deployment in healthy_deployments:
            model_id = self._get_model_id(deployment)
            if model_id is None:
                continue
            cache_key = CostLatencyBalancedMetricsLogger.get_deployment_cache_key(
                model_group=model_group,
                deployment_id=model_id,
            )
            state = self.router.cache.get_cache(key=cache_key) or {}
            deployment_state_map[model_id] = cast(Dict[str, Any], state)

        return self._select_from_states(
            model_group=model_group,
            healthy_deployments=healthy_deployments,
            deployment_state_map=deployment_state_map,
            now=now,
            messages=messages,
            input=input,
            request_kwargs=request_kwargs,
            request_counter=request_counter,
        )

    def _select_from_states(
        self,
        model_group: str,
        healthy_deployments: List[Dict[str, Any]],
        deployment_state_map: Dict[str, Dict[str, Any]],
        now: float,
        messages: Optional[List[Dict[str, str]]],
        input: Optional[Union[str, List]],
        request_kwargs: Optional[Dict[str, Any]],
        request_counter: float,
        ) -> Optional[Dict[str, Any]]:
        candidates = self._build_candidates(
            model_group=model_group,
            healthy_deployments=healthy_deployments,
            deployment_state_map=deployment_state_map,
            now=now,
            messages=messages,
            input=input,
        )
        if len(candidates) == 0:
            return None

        routing_mode = self._resolve_routing_mode(model_group)
        if routing_mode == "cost-first":
            selected_candidate, scored_candidates = self._select_cost_first_candidate(
                candidates=candidates
            )
            selected_reason = "lowest_cost_model_group_policy"
            slo_pass_candidates: List[Dict[str, Any]] = []
        elif routing_mode == "latency-first":
            selected_candidate, scored_candidates = (
                self._select_latency_first_candidate(candidates=candidates)
            )
            selected_reason = "lowest_latency_model_group_policy"
            slo_pass_candidates = []
        else:
            (
                selected_candidate,
                scored_candidates,
                selected_reason,
                slo_pass_candidates,
            ) = self._select_balanced_candidate(
                model_group=model_group,
                candidates=candidates,
                request_counter=request_counter,
            )

        if selected_candidate is None:
            return None

        self._attach_debug_metadata(
            request_kwargs=request_kwargs,
            candidates=candidates,
            scored_candidates=scored_candidates,
            selected_candidate=selected_candidate,
            selected_reason=selected_reason,
            slo_pass_ids=[c["deployment_id"] for c in slo_pass_candidates],
            model_group=model_group,
            routing_mode=routing_mode,
        )

        return cast(Dict[str, Any], selected_candidate["deployment"])

    def _select_balanced_candidate(
        self,
        model_group: str,
        candidates: List[Dict[str, Any]],
        request_counter: float,
    ) -> Tuple[
        Optional[Dict[str, Any]],
        List[Dict[str, Any]],
        str,
        List[Dict[str, Any]],
    ]:
        slo_threshold = self.routing_config.target_p95_ttft_seconds * (
            1 + self.routing_config.slo_margin
        )
        latency_slo_pass_candidates = [
            c
            for c in candidates
            if c["sample_count"] >= self.routing_config.min_samples_for_strict_slo
            and c["effective_ttft"] <= slo_threshold
        ]
        reliability_slo_pass_candidates = [
            c
            for c in latency_slo_pass_candidates
            if self._candidate_passes_reliability_gate(c)
        ]
        slo_pass_candidates = (
            reliability_slo_pass_candidates
            if len(reliability_slo_pass_candidates) > 0
            else latency_slo_pass_candidates
        )

        selected_reason = "best_score_slo_missed"
        selected_candidate: Optional[Dict[str, Any]] = None
        scored_candidates: List[Dict[str, Any]] = []

        if len(slo_pass_candidates) > 0:
            # Cold start guardrail: force exposure every N requests if eligible
            cold_start_candidates = [
                c
                for c in candidates
                if c["sample_count"] < self.routing_config.min_samples_for_strict_slo
                and c["is_hard_failed"] is False
            ]
            if (
                len(cold_start_candidates) > 0
                and int(request_counter) % self.routing_config.cold_start_exposure_interval
                == 0
            ):
                selected_candidate = self._random.choice(cold_start_candidates)
                selected_reason = "cold_start_forced_exposure"
                scored_candidates = slo_pass_candidates
            else:
                scored_candidates = self._score_candidates(
                    candidates=slo_pass_candidates,
                    weights=self.weights_when_slo_met,
                )
                selected_candidate = self._pick_best_candidate(scored_candidates)
                if len(reliability_slo_pass_candidates) > 0:
                    selected_reason = "best_score_slo_met_reliability_gate"
                else:
                    selected_reason = "best_score_slo_met_latency_only_fallback"

                # Bounded epsilon exploration (only inside SLO-pass set)
                if (
                    len(scored_candidates) > 1
                    and self._random.random() < self.routing_config.epsilon_explore
                ):
                    best_cost = min(c["cost"] for c in scored_candidates)
                    explore_pool = [
                        c
                        for c in scored_candidates
                        if c["cost"]
                        <= best_cost * self.routing_config.max_explore_cost_multiplier
                    ]
                    if len(explore_pool) > 1:
                        selected_candidate = self._random.choice(explore_pool)
                        if len(reliability_slo_pass_candidates) > 0:
                            selected_reason = "epsilon_explore_reliability_gate"
                        else:
                            selected_reason = "epsilon_explore_latency_only_fallback"
        else:
            scored_candidates = self._score_candidates(
                candidates=candidates,
                weights=self.weights_when_slo_missed,
            )
            selected_candidate = self._pick_best_candidate(scored_candidates)

        return (
            selected_candidate,
            scored_candidates,
            selected_reason,
            slo_pass_candidates,
        )

    def _build_candidates(
        self,
        model_group: str,
        healthy_deployments: List[Dict[str, Any]],
        deployment_state_map: Dict[str, Dict[str, Any]],
        now: float,
        messages: Optional[List[Dict[str, str]]],
        input: Optional[Union[str, List]],
    ) -> List[Dict[str, Any]]:
        try:
            input_tokens = token_counter(messages=messages, text=input)
        except Exception:
            input_tokens = 0

        candidates: List[Dict[str, Any]] = []
        for deployment in healthy_deployments:
            deployment_id = self._get_model_id(deployment)
            if deployment_id is None:
                continue

            state = deployment_state_map.get(deployment_id, {})

            # If deployment has recovered from cooldown, restart strategy learning
            # with a cold-start state instead of carrying over high failure streaks.
            if self._should_reset_state_after_cooldown(state, deployment_id):
                state = self._reset_state_for_recovery()
                deployment_state_map[deployment_id] = state
                cache_key = CostLatencyBalancedMetricsLogger.get_deployment_cache_key(
                    model_group=model_group,
                    deployment_id=deployment_id,
                )
                self.router.cache.set_cache(
                    key=cache_key,
                    value=state,
                    ttl=max(3600, int(self.routing_config.window_seconds * 3)),
                )

            CostLatencyBalancedMetricsLogger._prune_state_in_place(
                state=state,
                now=now,
                window_seconds=self.routing_config.window_seconds,
                buckets_to_keep=self.routing_config.abnormal_consecutive_windows + 3,
            )

            ttft_values = self._extract_ttft_values(state=state)
            sample_count = len(ttft_values)
            p95_ttft = self._percentile(ttft_values, 0.95) if sample_count > 0 else None
            ewma_ttft = state.get("ewma_ttft")

            if p95_ttft is not None and isinstance(ewma_ttft, (int, float)):
                effective_ttft = (
                    (1 - self.routing_config.ewma_alpha) * p95_ttft
                    + self.routing_config.ewma_alpha * float(ewma_ttft)
                )
            elif p95_ttft is not None:
                effective_ttft = p95_ttft
            elif isinstance(ewma_ttft, (int, float)):
                effective_ttft = float(ewma_ttft)
            else:
                effective_ttft = self.routing_config.target_p95_ttft_seconds * (
                    1 + self.routing_config.slo_margin
                )

            deployment_tpm = self._read_deployment_limit(deployment, "tpm")
            deployment_rpm = self._read_deployment_limit(deployment, "rpm")

            rpm_last_minute = self._count_recent_requests(state=state, now=now)
            tpm_last_minute = self._count_recent_tokens(state=state, now=now)
            rpm_util = (
                float(rpm_last_minute) / deployment_rpm
                if deployment_rpm not in (0, float("inf"))
                else 0.0
            )
            tpm_util = (
                float(tpm_last_minute) / deployment_tpm
                if deployment_tpm not in (0, float("inf"))
                else 0.0
            )
            load = max(rpm_util, tpm_util)

            if rpm_last_minute + 1 > deployment_rpm:
                continue
            if tpm_last_minute + input_tokens > deployment_tpm:
                continue

            request_count_window = max(
                1, len(cast(List[float], state.get("request_events", [])))
            )
            timeout_rate = (
                len(cast(List[float], state.get("timeout_events", [])))
                / request_count_window
            )
            five_xx_rate = (
                len(cast(List[float], state.get("http_5xx_events", [])))
                / request_count_window
            )

            penalty = min(
                1.0,
                timeout_rate * self.routing_config.failure_penalty_timeout
                + five_xx_rate * self.routing_config.failure_penalty_5xx,
            )

            consecutive_abnormal_windows = int(
                state.get("consecutive_abnormal_windows", 0)
            )
            is_hard_failed = (
                consecutive_abnormal_windows
                >= self.routing_config.abnormal_consecutive_windows
            )
            if is_hard_failed:
                penalty = min(1.0, penalty + 0.25)

            candidates.append(
                {
                    "deployment": deployment,
                    "deployment_id": deployment_id,
                    "cost": self._compute_deployment_cost(deployment),
                    "sample_count": sample_count,
                    "p95_ttft": p95_ttft,
                    "effective_ttft": effective_ttft,
                    "rpm_util": rpm_util,
                    "tpm_util": tpm_util,
                    "load": load,
                    "penalty": penalty,
                    "timeout_rate": timeout_rate,
                    "five_xx_rate": five_xx_rate,
                    "is_hard_failed": is_hard_failed,
                }
            )

        return candidates

    def _should_reset_state_after_cooldown(
        self, state: Dict[str, Any], model_id: str
    ) -> bool:
        if int(state.get("consecutive_abnormal_windows", 0)) < self.routing_config.abnormal_consecutive_windows:
            return False

        cooldown_key = CooldownCache.get_cooldown_cache_key(model_id)
        cooldown_state = self.router.cache.get_cache(key=cooldown_key, local_only=True)
        if cooldown_state is not None:
            return False
        return True

    @staticmethod
    def _reset_state_for_recovery() -> Dict[str, Any]:
        return {
            "ttft_samples": [],
            "request_events": [],
            "token_events": [],
            "timeout_events": [],
            "http_5xx_events": [],
            "window_stats": {},
            "ewma_ttft": None,
            "consecutive_abnormal_windows": 0,
            "last_cooldown_bucket": None,
        }

    def _score_candidates(
        self, candidates: List[Dict[str, Any]], weights: Tuple[float, float, float]
    ) -> List[Dict[str, Any]]:
        costs = [c["cost"] for c in candidates]
        latencies = [c["effective_ttft"] for c in candidates]
        loads = [c["load"] for c in candidates]

        min_cost, max_cost = min(costs), max(costs)
        min_latency, max_latency = min(latencies), max(latencies)
        min_load, max_load = min(loads), max(loads)

        scored_candidates: List[Dict[str, Any]] = []
        for candidate in candidates:
            cost_norm = self._normalize(
                candidate["cost"], lower=min_cost, upper=max_cost
            )
            latency_norm = self._normalize(
                candidate["effective_ttft"], lower=min_latency, upper=max_latency
            )
            load_norm = self._normalize(
                candidate["load"], lower=min_load, upper=max_load
            )

            score = (
                weights[0] * cost_norm
                + weights[1] * latency_norm
                + weights[2] * load_norm
                + candidate["penalty"]
            )
            enriched = dict(candidate)
            enriched.update(
                {
                    "score": score,
                    "cost_norm": cost_norm,
                    "latency_norm": latency_norm,
                    "load_norm": load_norm,
                    "weights": weights,
                }
            )
            scored_candidates.append(enriched)
        return scored_candidates

    def _pick_best_candidate(
        self, scored_candidates: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if len(scored_candidates) == 0:
            return None

        best_score = min(c["score"] for c in scored_candidates)
        tied_candidates = [
            c for c in scored_candidates if math.isclose(c["score"], best_score, rel_tol=1e-12, abs_tol=1e-12)
        ]
        return self._random.choice(tied_candidates)

    def _attach_debug_metadata(
        self,
        request_kwargs: Optional[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        scored_candidates: List[Dict[str, Any]],
        selected_candidate: Dict[str, Any],
        selected_reason: str,
        slo_pass_ids: List[str],
        model_group: str,
        routing_mode: ModelGroupRoutingMode,
    ) -> None:
        if request_kwargs is None:
            return
        metadata_field = self.metrics_logger._select_metadata_field(request_kwargs)
        if metadata_field is None:
            return
        request_kwargs.setdefault(metadata_field, {})
        metadata = request_kwargs[metadata_field]
        if not isinstance(metadata, dict):
            return

        score_breakdown: Dict[str, Dict[str, Any]] = {}
        scored_map = {c["deployment_id"]: c for c in scored_candidates}
        for candidate in candidates:
            deployment_id = candidate["deployment_id"]
            scored_candidate = scored_map.get(deployment_id, {})
            score_breakdown[deployment_id] = {
                "model_group": model_group,
                "cost": candidate["cost"],
                "effective_ttft": candidate["effective_ttft"],
                "load": candidate["load"],
                "penalty": candidate["penalty"],
                "timeout_rate": candidate["timeout_rate"],
                "five_xx_rate": candidate["five_xx_rate"],
                "reliability_gate_pass": self._candidate_passes_reliability_gate(
                    candidate
                ),
                "score": scored_candidate.get("score"),
                "cost_norm": scored_candidate.get("cost_norm"),
                "latency_norm": scored_candidate.get("latency_norm"),
                "load_norm": scored_candidate.get("load_norm"),
            }

        metadata["_slo_pass_set"] = slo_pass_ids
        metadata["_score_breakdown"] = score_breakdown
        metadata["_selected_reason"] = selected_reason
        metadata["_selected_deployment_id"] = selected_candidate.get("deployment_id")
        metadata["_resolved_routing_mode"] = routing_mode

    def _compute_deployment_cost(self, deployment: Dict[str, Any]) -> float:
        litellm_params = deployment.get("litellm_params", {}) or {}
        model_name = litellm_params.get("model")
        model_cost_map = litellm.model_cost.get(model_name, {}) if model_name else {}

        input_cost = litellm_params.get(
            "input_cost_per_token",
            model_cost_map.get("input_cost_per_token", 5.0),
        )
        output_cost = litellm_params.get(
            "output_cost_per_token",
            model_cost_map.get("output_cost_per_token", 5.0),
        )

        try:
            return max(0.0, float(input_cost) + float(output_cost))
        except Exception:
            return 10.0

    def _resolve_routing_mode(self, model_group: str) -> ModelGroupRoutingMode:
        return cast(
            ModelGroupRoutingMode,
            self.routing_config.per_model_group_routing.get(
                model_group, self.routing_config.default_routing_mode
            ),
        )

    def _select_cost_first_candidate(
        self, candidates: List[Dict[str, Any]]
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        scored_candidates = self._build_metric_ranked_candidates(
            candidates=candidates,
            metric_key="cost",
            metric_name="cost",
        )
        return self._pick_best_candidate(scored_candidates), scored_candidates

    def _select_latency_first_candidate(
        self, candidates: List[Dict[str, Any]]
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        scored_candidates = self._build_metric_ranked_candidates(
            candidates=candidates,
            metric_key="effective_ttft",
            metric_name="effective_ttft",
        )
        return self._pick_best_candidate(scored_candidates), scored_candidates

    def _build_metric_ranked_candidates(
        self,
        candidates: List[Dict[str, Any]],
        metric_key: str,
        metric_name: str,
    ) -> List[Dict[str, Any]]:
        scored_candidates: List[Dict[str, Any]] = []
        for candidate in candidates:
            metric_value = float(candidate.get(metric_key, float("inf")))
            enriched = dict(candidate)
            enriched.update(
                {
                    "score": metric_value,
                    "ranking_metric": metric_name,
                    "cost_norm": None,
                    "latency_norm": None,
                    "load_norm": None,
                    "weights": None,
                }
            )
            scored_candidates.append(enriched)
        return scored_candidates

    def _candidate_passes_reliability_gate(self, candidate: Dict[str, Any]) -> bool:
        max_timeout_rate = self.routing_config.max_timeout_rate_for_slo_pass
        timeout_rate = candidate.get("timeout_rate")
        if (
            max_timeout_rate is not None
            and isinstance(timeout_rate, (int, float))
            and float(timeout_rate) > float(max_timeout_rate)
        ):
            return False

        max_5xx_rate = self.routing_config.max_5xx_rate_for_slo_pass
        five_xx_rate = candidate.get("five_xx_rate")
        if (
            max_5xx_rate is not None
            and isinstance(five_xx_rate, (int, float))
            and float(five_xx_rate) > float(max_5xx_rate)
        ):
            return False

        return True

    @staticmethod
    def _normalize(value: float, lower: float, upper: float) -> float:
        if math.isclose(lower, upper, rel_tol=1e-12, abs_tol=1e-12):
            return 0.0
        return (value - lower) / (upper - lower)

    @staticmethod
    def _normalize_weights(weights: Tuple[float, float, float]) -> Tuple[float, float, float]:
        total = float(weights[0]) + float(weights[1]) + float(weights[2])
        if total <= 0:
            return (0.85, 0.05, 0.10)
        return (
            float(weights[0]) / total,
            float(weights[1]) / total,
            float(weights[2]) / total,
        )

    @staticmethod
    def _read_deployment_limit(deployment: Dict[str, Any], field_name: str) -> float:
        value = (
            deployment.get(field_name)
            or deployment.get("litellm_params", {}).get(field_name)
            or deployment.get("model_info", {}).get(field_name)
        )
        if value is None:
            return float("inf")
        try:
            casted = float(value)
            if casted <= 0:
                return float("inf")
            return casted
        except Exception:
            return float("inf")

    @staticmethod
    def _extract_ttft_values(state: Dict[str, Any]) -> List[float]:
        values: List[float] = []
        for item in state.get("ttft_samples", []) or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                value = item[1]
                if isinstance(value, (float, int)):
                    values.append(float(value))
        return values

    @staticmethod
    def _count_recent_requests(state: Dict[str, Any], now: float) -> int:
        cutoff = now - 60
        count = 0
        for ts in state.get("request_events", []) or []:
            if isinstance(ts, (int, float)) and float(ts) >= cutoff:
                count += 1
        return count

    @staticmethod
    def _count_recent_tokens(state: Dict[str, Any], now: float) -> int:
        cutoff = now - 60
        total = 0
        for item in state.get("token_events", []) or []:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            ts, token_count = item
            if isinstance(ts, (int, float)) and float(ts) >= cutoff:
                if isinstance(token_count, (int, float)):
                    total += int(token_count)
        return total

    @staticmethod
    def _percentile(values: List[float], quantile: float) -> Optional[float]:
        if len(values) == 0:
            return None
        ordered = sorted(values)
        position = max(0, int(math.ceil(quantile * len(ordered))) - 1)
        position = min(position, len(ordered) - 1)
        return float(ordered[position])

    @staticmethod
    def _get_model_id(deployment: Dict[str, Any]) -> Optional[str]:
        deployment_id = deployment.get("model_info", {}).get("id")
        if deployment_id is None:
            return None
        if isinstance(deployment_id, int):
            deployment_id = str(deployment_id)
        return str(deployment_id)
