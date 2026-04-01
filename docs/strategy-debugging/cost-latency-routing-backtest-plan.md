# Cost-Latency Routing Backtest Plan

## Summary

- Goal: convert exported LiteLLM request logs into a multi-deployment routing backtest dataset.
- Focus: do not reconstruct historical routing decisions exactly. Build a realistic and reproducible evaluation dataset where each request has multiple deployment candidates.
- Primary use cases:
  - compare `cost-latency-balanced`, `latency-first`, and `cost-first`
  - tune weights, penalties, exploration, and cold-start behavior
  - produce a report that is good enough for strategy review and staged rollout decisions
- Current decision:
  - phase 1 still uses one unified balanced config as the default baseline
  - the strategy now supports per-model-group routing mode selection when needed
  - supported routing modes are `balanced`, `cost-first`, and `latency-first`

## Scope

- Initial profiling started from `ai-seek-gemini-flash-lite`
- Current validation scope now includes:
  - `ai-seek-gemini-flash-lite`
  - `ai-seek-fast-small`
  - `ai-seek-claude-sonnet`
- Use LiteLLM exported logs only. Do not use the database.
- Use simple, explainable imputation. Do not build a full causal simulator.
- Optimize for fast iteration, reproducibility, and debuggability.

## Current Status

- Completed:
  - implemented the custom routing strategy in LiteLLM
  - added router unit tests for SLO filtering, degradation mode, cold start, and cooldown behavior
  - built log export, profiling, synthetic candidate generation, and replay backtest scripts
  - exported and profiled a multi-model historical dataset from LiteLLM logs
  - validated the strategy on three representative model groups
- Current rollout recommendation:
  - use one unified `cost-latency-balanced` config in phase 1
  - do not branch by model group on day 1 unless live observations show a clear reason
  - keep per-model-group mode overrides available as an operational escape hatch
- Unified rollout candidate:
  - `target_p95_ttft_seconds = 5.0`
  - `slo_margin = 0.10`
  - `max_timeout_rate_for_slo_pass = 0.02`
  - `max_5xx_rate_for_slo_pass = 0.06`
  - `weights_when_slo_met = (0.85, 0.05, 0.10)`
  - `weights_when_slo_missed = (0.15, 0.75, 0.10)`
  - `default_routing_mode = "balanced"`
  - `per_model_group_routing = {}`

## Unified Strategy Recommendation

- Recommended phase 1 production config:
  - `target_p95_ttft_seconds = 5.0`
  - `slo_margin = 0.10`
  - `window_seconds = 600`
  - `min_samples_for_strict_slo = 30`
  - `max_timeout_rate_for_slo_pass = 0.02`
  - `max_5xx_rate_for_slo_pass = 0.06`
  - `epsilon_explore = 0.05`
  - `weights_when_slo_met = (0.85, 0.05, 0.10)`
  - `weights_when_slo_missed = (0.15, 0.75, 0.10)`
  - `failure_penalty_timeout = 0.5`
  - `failure_penalty_5xx = 0.3`
  - `default_routing_mode = "balanced"`
  - `per_model_group_routing = {}`
- Why this is the current unified recommendation:
  - it is the best cross-model compromise among the tested settings
  - it materially reduces cost relative to `latency-first` on both `ai-seek-gemini-flash-lite` and `ai-seek-claude-sonnet`
  - it stays latency-safe on `ai-seek-fast-small`, where balanced routing is effectively neutral
  - it avoids the stronger model-group specialization and operational complexity of maintaining multiple routing policies from day 1
- Known limitation of the unified recommendation:
  - on `ai-seek-gemini-flash-lite`, `cost-first` is still cheaper than balanced under a `5s` target
  - this means `5s` is generous enough that the balanced strategy is acting as a safer global compromise, not a per-group optimum
  - this tradeoff is acceptable for phase 1 if the product goal is one policy everywhere

## Per-Model-Group Mode Support

- The strategy object now supports choosing routing mode per model group without changing the Router public interface.
- Keep using:
  - `router.set_custom_routing_strategy(...)`
- New config fields:
  - `default_routing_mode`
  - `per_model_group_routing`
- Supported values:
  - `balanced`
  - `cost-first`
  - `latency-first`
- Current recommendation:
  - keep `default_routing_mode = "balanced"`
  - only add entries to `per_model_group_routing` for model groups that prove they need specialization
- Current non-goal:
  - per-model-group independent numeric parameters are not implemented yet
  - all model groups still share the same SLO threshold, weights, penalties, and exploration settings

## Runtime Update Path

- The strategy now supports runtime config refresh through:
  - `strategy.update_routing_config(...)`
- This updates weights, SLO thresholds, routing modes, and logger TTL without reinstalling the strategy object.
- Rolling metric state in cache is preserved.
- Recommended use:
  - use `update_routing_config(...)` for small live tuning
  - use a normal deploy only when you are changing code, not just config

## Example Config

```python
strategy = CostLatencyBalancedRouting(
    router=router,
    routing_config={
        "target_p95_ttft_seconds": 5.0,
        "slo_margin": 0.10,
        "max_timeout_rate_for_slo_pass": 0.02,
        "max_5xx_rate_for_slo_pass": 0.06,
        "weights_when_slo_met": (0.85, 0.05, 0.10),
        "weights_when_slo_missed": (0.15, 0.75, 0.10),
        "default_routing_mode": "balanced",
        "per_model_group_routing": {
            "ai-seek-gemini-flash-lite": "cost-first",
            "ai-seek-fast-small": "latency-first",
        },
    },
)
router.set_custom_routing_strategy(strategy)
```

```python
strategy.update_routing_config(
    per_model_group_routing={
        "ai-seek-gemini-flash-lite": "balanced",
        "ai-seek-fast-small": "latency-first",
    }
)
```

## Workspace Layout

- Scripts:
  - `/Users/wenyu/Documents/code/guru-litellm/scripts/profile_routing_export.py`
  - `/Users/wenyu/Documents/code/guru-litellm/scripts/build_synthetic_routing_dataset.py`
  - `/Users/wenyu/Documents/code/guru-litellm/scripts/run_routing_backtest.py`
- Input root:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/`
- Output root:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/<dataset_name>/`

## Current Local Paths

- Existing export roots detected locally:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_03_11_2026_03_11`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11`
- Current files confirmed in the longer export window:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/raw_logs.jsonl`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/export_state.json`
- Recommended derived dataset root for the first profiling/backtest pipeline:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/`
- Recommended derived outputs:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/request_base.parquet`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/deployment_time_profiles.parquet`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/dataset_overview.json`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/deployment_coverage.csv`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/synthetic_request_candidates.parquet`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/backtest_results.parquet`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/backtest_summary.json`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/backtest_report.md`

## Current Tuning Snapshot

- Primary tuning dataset:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-gemini-flash-lite`
- Guardrail dataset:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-fast-small`
- Secondary representative dataset:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-claude-sonnet`
- Tune search outputs:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-gemini-flash-lite/backtests/tune_search/`
- Eval search outputs:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-gemini-flash-lite/backtests/eval_search/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-fast-small/backtests/eval_search/`
- `5s` target search outputs:
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-gemini-flash-lite/backtests/eval_search_p95_5s/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-gemini-flash-lite/backtests/eval_search_p95_5s_round2/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-fast-small/backtests/eval_search_p95_5s/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-fast-small/backtests/eval_search_p95_5s_round2/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-claude-sonnet/backtests/tune_search_p95_5s/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-claude-sonnet/backtests/eval_p95_5s_candidate/`
  - `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/flash_lite_2026_02_26_2026_03_11/derived/ai-seek-claude-sonnet/backtests/eval_search_p95_5s_round2/`
- Historical `3s` candidate kept for reference:
  - `slo_margin = 0.20`
  - `max_timeout_rate_for_slo_pass = 0.02`
  - `max_5xx_rate_for_slo_pass = 0.06`
  - `weights_when_slo_met = (0.75, 0.15, 0.10)`
- Why it is no longer the phase 1 rollout default:
  - it was a strong fit for `ai-seek-gemini-flash-lite`
  - but the broader cross-model tests suggest the `5s` candidate is a better single-policy compromise for initial rollout

## `5s` Target Snapshot

- Candidate config with the best cross-model behavior so far:
  - `target_p95_ttft_seconds = 5.0`
  - `slo_margin = 0.10`
  - `max_timeout_rate_for_slo_pass = 0.02`
  - `max_5xx_rate_for_slo_pass = 0.06`
  - `weights_when_slo_met = (0.85, 0.05, 0.10)`
- Eval behavior on `ai-seek-gemini-flash-lite`:
  - `latency-first`: `avg_cost=0.00029675`, `p95_ttft=2429.12ms`, `success_rate=92.33%`
  - `balanced`: `avg_cost=0.00024528`, `p95_ttft=3429.41ms`, `success_rate=98.25%`
  - `cost-first`: `avg_cost=0.00023239`, `p95_ttft=3489.13ms`, `success_rate=99.38%`
- Eval behavior on `ai-seek-claude-sonnet`:
  - `latency-first`: `avg_cost=0.08850646`, `p95_ttft=3364.26ms`, `success_rate=100.00%`
  - `balanced`: `avg_cost=0.06533290`, `p95_ttft=4611.43ms`, `success_rate=100.00%`
  - `cost-first`: `avg_cost=0.04310660`, `p95_ttft=6443.07ms`, `success_rate=99.01%`
- Guardrail check on `ai-seek-fast-small`:
  - `balanced`: `avg_cost=0.00007383`, `p95_ttft=1255.04ms`, `success_rate=100.00%`
- Interpretation:
  - `5s` makes the balanced strategy meaningfully cheaper than `latency-first` on both representative chat model groups.
  - On noisier `gemini-flash-lite`, the strategy still stays well under `5s` while recovering substantial success rate.
  - On `claude-sonnet`, the strategy cuts cost materially without violating the `5s` target, while `cost-first` overshoots the latency target.
  - As a single global policy, this is the current best tested compromise.

## Phase 1 Rollout Plan

- Goal:
  - ship one unified `cost-latency-balanced` strategy config
  - validate that the backtest gains hold in live traffic
- Rollout steps:
  - shadow mode with decision logging only
  - `10%` traffic
  - `50%` traffic
  - `100%` traffic
- Rollback rule:
  - remove `router.set_custom_routing_strategy(...)`
  - fall back to the previous router behavior immediately
- Required live checks per rollout stage:
  - overall `P95 TTFT`
  - per-model-group `P95 TTFT`
  - overall and per-model-group success rate
  - overall and per-model-group average request cost
  - deployment share drift
  - recent timeout and `5xx` rates
- Exit criteria for phase 1:
  - no material regression on global error rate
  - no unacceptable latency regression on core model groups
  - cost improvement versus `latency-first` remains visible on aggregate traffic

## Post-Deploy Iteration Plan

- The strategy already adapts online to recent latency, load, timeout, and `5xx` changes through rolling window state.
- Phase 1 does not auto-learn parameters online.
- Parameter updates should be manual and controlled:
  - adjust config via `update_routing_config(...)` or by replacing the strategy object
  - observe for at least one traffic cycle
- First tuning loop after rollout:
  - keep the unified `5s` config for the first observation cycle
  - review one-day and three-day live metrics
  - only then decide whether to stay unified or introduce per-model-group mode overrides

## Live Observation Checklist

- Observation windows:
  - shadow mode: at least `2` hours
  - `10%` traffic: at least `4` hours
  - `50%` traffic: at least `12` hours
  - `100%` traffic: at least `24` hours before calling the rollout stable
- Core aggregate metrics:
  - request count
  - `P50 TTFT`
  - `P95 TTFT`
  - `P99 TTFT`
  - success rate
  - timeout rate
  - `5xx` rate
  - average request cost
  - total spend per hour
- Core breakdown metrics:
  - top model-group `P95 TTFT`
  - top model-group success rate
  - top model-group average request cost
  - deployment share by model group
  - deployment cooldown count
  - deployment timeout and `5xx` rate
- Recommended comparison baselines:
  - previous production routing strategy
  - same day previous week if traffic shape has strong hourly seasonality
  - immediate pre-rollout window for short-term sanity checks
- Suggested go / no-go thresholds for phase 1:
  - aggregate `P95 TTFT` should not regress by more than `15%` versus baseline for `3` consecutive windows
  - aggregate success rate should not drop by more than `1.0pp` versus baseline for `3` consecutive windows
  - aggregate timeout or `5xx` rate should not exceed `2x` baseline for `3` consecutive windows
  - aggregate average request cost should be flat or down by the `50%` traffic stage
  - any core model group with a severe latency or reliability regression should block moving to the next rollout stage
- Immediate rollback conditions:
  - sustained timeout spike on multiple core model groups
  - sustained `5xx` spike on multiple core model groups
  - unexpected deployment concentration caused by a misconfiguration
  - total cost increases materially without a compensating latency or reliability gain

## Shadow Logging Checklist

- Log a sampled subset of routing decisions during shadow mode and early partial rollout.
- Recommended sampled fields:
  - `_selected_deployment_id`
  - `_selected_reason`
  - `_slo_pass_set`
  - `_score_breakdown`
- Why these fields matter:
  - `_selected_deployment_id`: confirms which deployment actually won
  - `_selected_reason`: shows whether the decision came from normal scoring, epsilon exploration, cold start exposure, or degraded routing
  - `_slo_pass_set`: explains which deployments survived the SLO and reliability gate
  - `_score_breakdown`: explains cost, latency, load, penalty, and normalized score terms per candidate
- Sampling recommendation:
  - `1%` to `5%` of requests is enough for operator debugging
  - always sample failures and slow requests even if the base sample rate is lower
- Validation before rollout:
  - confirm these fields are preserved through the logging pipeline
  - confirm they are queryable in the proxy logs or downstream observability store
  - confirm sampled logs can be grouped by `model_group` and `selected_deployment_id`

## Daily Review Template

- Traffic:
  - total requests
  - top model groups by volume
- Latency:
  - aggregate `P95 TTFT`
  - top model-group `P95 TTFT`
  - largest latency regressions versus baseline
- Reliability:
  - aggregate success rate
  - aggregate timeout and `5xx` rates
  - top model-group regressions versus baseline
- Cost:
  - aggregate average request cost
  - top model-group average request cost
  - savings versus baseline routing
- Routing behavior:
  - deployment share drift
  - unexpected concentration on one deployment
  - cooldown events and abnormal-window streaks
- Decision:
  - keep current stage
  - progress to next stage
  - rollback and inspect sampled routing logs

## Inputs

- Required:
  - `clean_requests.parquet`
  - `deployment_hourly_stats.parquet`
- Optional:
  - `deployment_pricing.csv`
  - `deployment_limits.csv`

## Dataset Split

- Split by time to avoid future leakage.
- Default split ratios:
  - `train = 60%`
  - `tune = 20%`
  - `eval = 20%`
- If the export window is short, enforce:
  - `train >= 7 days`
  - `tune >= 2 days`
  - `eval >= 2 days`
- Usage:
  - `train`: build profiles and donor pools
  - `tune`: tune strategy parameters
  - `eval`: final comparison and report

## Phase 1: Profiling And Request Base Table

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/profile_routing_export.py`

### CLI

- `--input-dir`
- `--model-group`
- `--out-dir`
- `--split-mode` with default `time`
- `--train-ratio`
- `--tune-ratio`
- `--eval-ratio`
- `--min-deployment-requests` with default `50`
- `--min-deployment-covered-hours` with default `12`

### Processing

1. Read `clean_requests.parquet`
2. Filter `model_group == ai-seek-gemini-flash-lite`
3. Deduplicate by `request_id`
4. Derive:
  - `request_time_utc`
  - `hour_utc`
  - `date_utc`
  - `day_of_week`
  - `hour_of_day`
  - `is_timeout`
  - `is_5xx`
  - `split`

### Error Classification

- Mark `is_timeout = 1` when:
  - `status == failure` and `error_class` contains `Timeout`
  - or `error_code` contains `timeout`
- Mark `is_5xx = 1` when:
  - `error_code` is in `500-599`
  - or `error_class` clearly indicates provider/server failure
- Otherwise treat as generic failure

### Output: Request Base

Write:

- `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/request_base.parquet`

Fields:

- `request_id`
- `model_group`
- `request_time_utc`
- `date_utc`
- `hour_utc`
- `day_of_week`
- `hour_of_day`
- `split`
- `actual_deployment_id`
- `actual_status`
- `actual_ttft_ms`
- `actual_latency_ms`
- `actual_spend_usd`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `team_id`
- `end_user`
- `is_timeout`
- `is_5xx`

### Output: Dataset Inventory

Write:

- `dataset_overview.json`
- `deployment_coverage.csv`

Include:

- total request count
- train/tune/eval request counts
- deployment count
- per-deployment request counts
- per-deployment covered hours
- sparse deployment list

## Phase 2: Deployment Time Profiles

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/profile_routing_export.py`

### Training Data Only

- Build profiles from `train` only
- Do not use `tune` or `eval` when creating priors

### Profile Levels

Build all five levels:

1. `hourly`
  - key: `deployment_id + hour_utc`
2. `weekly_hour`
  - key: `deployment_id + day_of_week + hour_of_day`
3. `deployment_global`
  - key: `deployment_id`
4. `provider_global`
  - key: `custom_llm_provider`
5. `fleet_global`
  - key: `model_group`

### Output

Write:

- `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/deployment_time_profiles.parquet`

Fields:

- `profile_level`
- `model_group`
- `deployment_id`
- `custom_llm_provider`
- `hour_utc`
- `day_of_week`
- `hour_of_day`
- `sample_count`
- `success_rate`
- `failure_rate`
- `timeout_rate`
- `rate_5xx`
- `avg_ttft_ms`
- `p50_ttft_ms`
- `p95_ttft_ms`
- `avg_latency_ms`
- `p95_latency_ms`
- `avg_spend_usd`
- `avg_prompt_tokens`
- `avg_completion_tokens`
- `avg_total_tokens`

### Sparsity Rule

- `sample_count >= 20` means the profile level is directly usable
- `sample_count < 20` means the builder may fall back to the next profile level

## Phase 3: Candidate Pool Definition

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/build_synthetic_routing_dataset.py`

### Candidate Eligibility

- Default candidate set includes deployments seen in `train`
- Eligibility threshold:
  - `request_count >= 50`
  - or `covered_hours >= 12`
- Deployments below threshold but with some history are marked as `cold_start_candidate`
- Do not include deployments with zero historical samples in v1

### Candidate Expansion

- For every `tune` and `eval` request
- Enumerate all eligible deployments under the model group
- Create one row per `request_id + candidate_deployment_id`

## Phase 4: Separate Decision Features From Simulated Outcomes

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/build_synthetic_routing_dataset.py`

### Feature Layer

Decision-time estimates only. These are the values routing strategies can read.

Fields:

- `feature_cost_usd`
- `feature_p50_ttft_ms`
- `feature_p95_ttft_ms`
- `feature_failure_rate`
- `feature_timeout_rate`
- `feature_5xx_rate`
- `feature_sample_count`

### Simulation Layer

These are the values returned by the environment only after a candidate is selected.

Fields:

- `sim_status`
- `sim_ttft_ms`
- `sim_latency_ms`
- `sim_spend_usd`
- `sim_is_timeout`
- `sim_is_5xx`
- `sim_error_class`

### Rule

- Backtest strategies must never read `sim_*` before selection.
- `sim_*` is used after selection to:
  - update online rolling statistics
  - compute final backtest metrics

## Phase 5: Feature Imputation Rules

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/build_synthetic_routing_dataset.py`

### Imputation Priority

For request time `t` and deployment `d`, resolve `feature_*` in this order:

1. `hourly`
2. `weekly_hour`
3. `deployment_global`
4. `provider_global`
5. `fleet_global`

### Required Metadata

Every candidate row must include:

- `feature_impute_level`
- `feature_is_imputed`

### Cost Feature Rule

Priority:

1. If static pricing exists, recompute cost from request token counts
2. Otherwise estimate `usd_per_token` from train data for the deployment
3. Otherwise fall back to `avg_spend_usd`

Also include:

- `cost_source`
- `feature_unit_cost_usd_per_token`

## Phase 6: Simulation Layer Generation

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/build_synthetic_routing_dataset.py`

### Actual Selected Deployment

- If `candidate_deployment_id == actual_deployment_id`
- Then all `sim_*` fields must equal the real observed log values

### Unselected Deployments

Use donor bootstrap rather than hard-copying profile means.

Donor selection priority:

1. same `deployment + weekly_hour`
2. same deployment global pool
3. same provider pool
4. fleet global pool

### Donor Sampling Rule

- Use a fixed random seed for reproducibility
- Suggested seed:
  - `hash(request_id + candidate_deployment_id + global_seed)`
- Donor provides:
  - status
  - ttft
  - latency
  - error type
- Spend should not be copied from the donor blindly
- Prefer recomputing spend using current request tokens and candidate pricing

### Light Noise

- Apply `5%-15%` multiplicative noise to `sim_ttft_ms` and `sim_latency_ms` for synthetic candidates
- Do not add large noise to failure probabilities
- Use deterministic seeding for all noise

### Required Metadata

Every candidate row must include:

- `sim_source_level`
- `sim_donor_request_id`
- `sim_random_seed`

## Phase 7: Synthetic Candidate Dataset

Write:

- `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/synthetic_request_candidates.parquet`

Fields:

- `request_id`
- `split`
- `request_time_utc`
- `hour_utc`
- `day_of_week`
- `hour_of_day`
- `actual_deployment_id`
- `candidate_deployment_id`
- `is_actual_selected`
- `custom_llm_provider`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `feature_cost_usd`
- `feature_p50_ttft_ms`
- `feature_p95_ttft_ms`
- `feature_failure_rate`
- `feature_timeout_rate`
- `feature_5xx_rate`
- `feature_sample_count`
- `feature_is_imputed`
- `feature_impute_level`
- `feature_unit_cost_usd_per_token`
- `cost_source`
- `sim_status`
- `sim_ttft_ms`
- `sim_latency_ms`
- `sim_spend_usd`
- `sim_is_timeout`
- `sim_is_5xx`
- `sim_error_class`
- `sim_source_level`
- `sim_donor_request_id`
- `sim_random_seed`

## Phase 8: Capacity And Load Estimation

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/run_routing_backtest.py`

### If Deployment Limits Exist

Read:

- `rpm_limit`
- `tpm_limit`

### If Limits Do Not Exist

Estimate soft capacity from `train`:

- `rpm_limit = max(10, ceil(1.5 * p95(hourly request_count / 60)))`
- `tpm_limit = max(1000, ceil(1.5 * p95(hourly total_tokens / 60)))`

### Online Load State

During replay, maintain:

- last 60 second request count
- last 60 second token count

Derived fields:

- `rpm_util = current_rpm / rpm_limit`
- `tpm_util = current_tpm / tpm_limit`
- `load_util = max(rpm_util, tpm_util)`

## Phase 9: Backtest Runner

Implemented by:

- `/Users/wenyu/Documents/code/guru-litellm/scripts/run_routing_backtest.py`

### CLI

- `--dataset-dir`
- `--split`
- `--strategy`
- `--global-seed`
- `--target-p95-ttft-seconds`
- `--slo-margin`
- `--window-seconds`
- `--min-samples-for-strict-slo`
- `--epsilon-explore`
- `--weights-when-slo-met`
- `--weights-when-slo-missed`
- `--failure-penalty-timeout`
- `--failure-penalty-5xx`
- `--abnormal-timeout-rate-threshold`
- `--abnormal-5xx-rate-threshold`
- `--abnormal-consecutive-windows`

### Replay Order

- Replay strictly in ascending `request_time_utc`
- Each decision may only use current and past state

### Per-Deployment Online State

Maintain:

- rolling outcome window of selected requests over `window_seconds`
- EWMA-smoothed metrics
- consecutive abnormal window counter
- cooldown deadline
- cold-start exposure counters

### Balanced Strategy

Mirror the intended production routing logic:

1. Stage 1: SLO filter
2. Stage 2: score cost, latency, load, and penalties
3. apply epsilon exploration within SLO-passing candidates
4. enforce cold-start exposure floor
5. apply abnormal-window penalty and cooldown
6. after cooldown recovery, clear online learning state and treat as cold-start again

### Baseline Strategies

- `latency-first`
  - select candidate with lowest `feature_p95_ttft_ms`
- `cost-first`
  - select candidate with lowest `feature_cost_usd`

### Required Debug Metadata

Store equivalents of:

- `_slo_pass_set`
- `_score_breakdown`
- `_selected_reason`

Recommended output fields:

- `debug_slo_pass_set_json`
- `debug_score_breakdown_json`
- `debug_selected_reason`

## Phase 10: Backtest Outputs

Write:

- `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/backtest_results.parquet`
- `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/backtest_summary.json`
- `/Users/wenyu/Documents/code/guru-litellm/data/routing_backtest/backtest_report.md`

### Per-Request Result Fields

- `request_id`
- `strategy_name`
- `selected_deployment_id`
- `selected_rank`
- `selected_score`
- `selected_status`
- `selected_ttft_ms`
- `selected_latency_ms`
- `selected_spend_usd`
- `selected_is_timeout`
- `selected_is_5xx`
- `rpm_util`
- `tpm_util`
- `load_util`
- `debug_slo_pass_set_json`
- `debug_score_breakdown_json`
- `debug_selected_reason`

### Summary Metrics

- `request_count`
- `avg_cost_per_request`
- `p50_ttft_ms`
- `p95_ttft_ms`
- `success_rate`
- `failure_rate`
- `timeout_rate`
- `rate_5xx`
- `slo_violation_rate`
- `deployment_share`

## Phase 11: Tuning And Reporting

### Tuning Order

1. tune `weights_when_slo_met`
2. tune `weights_when_slo_missed`
3. tune `epsilon_explore`
4. tune penalties and abnormal thresholds

### Required Report Sections

- dataset overview
- deployment coverage
- imputation coverage
- overall strategy comparison
- peak-hour comparison
- cold-start behavior
- abnormal-window behavior
- recommended production parameters

## Validation Rules

### Dataset Validation

- every `request_id` in `synthetic_request_candidates` has at least 2 candidates
- every `request_id` has exactly 1 `is_actual_selected = true`
- for the actual selected candidate, `sim_*` equals the real observed values
- `feature_p95_ttft_ms >= feature_p50_ttft_ms`
- `sim_latency_ms >= sim_ttft_ms`

### Backtest Validation

- no request may use future state
- cooldown deployments must not be selected
- `balanced` should have lower `slo_violation_rate` than `cost-first`
- `balanced` should have lower `avg_cost_per_request` than `latency-first`

## Test Plan

### `profile_routing_export.py`

- verify time split correctness on a small sample
- verify profile fallback behavior
- verify timeout and 5xx classification

### `build_synthetic_routing_dataset.py`

- verify candidate expansion per request
- verify donor bootstrap reproducibility
- verify actual selected row is preserved
- verify separation between feature layer and simulation layer

### `run_routing_backtest.py`

- verify all three strategies run end-to-end
- verify balanced strategy SLO filtering
- verify penalty and cooldown behavior
- verify debug fields are persisted

## Milestones

1. Build `profile_routing_export.py`
  - produce `request_base.parquet`
  - produce `deployment_time_profiles.parquet`
  - produce `dataset_overview.json`
2. Build `build_synthetic_routing_dataset.py`
  - produce `synthetic_request_candidates.parquet`
3. Build `run_routing_backtest.py`
  - produce `backtest_results.parquet`
  - produce `backtest_report.md`

## Defaults

- `model_group = ai-seek-gemini-flash-lite`
- `global_seed = 20260313`
- `min_deployment_requests = 50`
- `min_deployment_covered_hours = 12`
- `profile_min_samples = 20`
- `noise_range = 5%-15%`
- `target_p95_ttft_seconds = 3.0`
- `slo_margin = 0.05`
- `window_seconds = 600`

## Next Implementation Order

1. implement `profile_routing_export.py`
2. implement `build_synthetic_routing_dataset.py`
3. implement `run_routing_backtest.py`
