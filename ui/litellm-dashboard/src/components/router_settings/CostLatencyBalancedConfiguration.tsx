import React from "react";

interface CostLatencyBalancedConfigurationProps {
  customRoutingStrategyArgs?: {
    default_routing_mode?: string;
    target_p95_ttft_seconds?: number;
    slo_margin?: number;
    min_samples_for_strict_slo?: number;
    cold_start_floor?: number;
    cold_start_exposure_interval?: number;
    max_timeout_rate_for_slo_pass?: number | null;
    max_5xx_rate_for_slo_pass?: number | null;
    per_model_group_routing?: Record<string, string>;
  };
}

const DEFAULT_COST_LATENCY_BALANCED_ARGS = {
  target_p95_ttft_seconds: 5.0,
  slo_margin: 0.1,
  min_samples_for_strict_slo: 30,
  cold_start_floor: 5,
  cold_start_exposure_interval: 20,
  max_timeout_rate_for_slo_pass: 0.02,
  max_5xx_rate_for_slo_pass: 0.06,
} as const;

const CostLatencyBalancedConfiguration: React.FC<CostLatencyBalancedConfigurationProps> = ({
  customRoutingStrategyArgs,
}) => {
  const defaultRoutingMode = customRoutingStrategyArgs?.default_routing_mode || "balanced";
  const targetP95TtftSeconds =
    customRoutingStrategyArgs?.target_p95_ttft_seconds ??
    DEFAULT_COST_LATENCY_BALANCED_ARGS.target_p95_ttft_seconds;
  const sloMargin = customRoutingStrategyArgs?.slo_margin ?? DEFAULT_COST_LATENCY_BALANCED_ARGS.slo_margin;
  const minSamplesForStrictSlo =
    customRoutingStrategyArgs?.min_samples_for_strict_slo ??
    DEFAULT_COST_LATENCY_BALANCED_ARGS.min_samples_for_strict_slo;
  const coldStartFloor =
    customRoutingStrategyArgs?.cold_start_floor ??
    DEFAULT_COST_LATENCY_BALANCED_ARGS.cold_start_floor;
  const coldStartExposureInterval =
    customRoutingStrategyArgs?.cold_start_exposure_interval ??
    DEFAULT_COST_LATENCY_BALANCED_ARGS.cold_start_exposure_interval;
  const maxTimeoutRateForSloPass =
    customRoutingStrategyArgs?.max_timeout_rate_for_slo_pass ??
    DEFAULT_COST_LATENCY_BALANCED_ARGS.max_timeout_rate_for_slo_pass;
  const max5xxRateForSloPass =
    customRoutingStrategyArgs?.max_5xx_rate_for_slo_pass ??
    DEFAULT_COST_LATENCY_BALANCED_ARGS.max_5xx_rate_for_slo_pass;
  const perModelGroupRouting = customRoutingStrategyArgs?.per_model_group_routing || {};

  return (
    <>
      <div className="space-y-6">
        <div className="max-w-3xl">
          <h3 className="text-sm font-medium text-gray-900">Cost-Latency Balanced Configuration</h3>
          <p className="text-xs text-gray-500 mt-1">
            Configure the fused routing policy and per-model-group routing mode overrides.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-2">
            <label htmlFor="cost-latency-default-routing-mode" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Default Routing Mode
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Default policy applied when a model group does not have its own override.
              </p>
            </label>
            <select
              aria-label="Default Routing Mode"
              id="cost-latency-default-routing-mode"
              name="cost_latency_default_routing_mode"
              defaultValue={defaultRoutingMode}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            >
              <option value="balanced">balanced</option>
              <option value="cost-first">cost-first</option>
              <option value="latency-first">latency-first</option>
            </select>
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-target-p95-ttft-seconds" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Target P95 TTFT (seconds)
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Target time-to-first-token SLO before the strategy treats a deployment as degraded.
              </p>
            </label>
            <input
              aria-label="Target P95 TTFT (seconds)"
              id="cost-latency-target-p95-ttft-seconds"
              name="cost_latency_target_p95_ttft_seconds"
              type="number"
              step="0.1"
              min="0"
              defaultValue={targetP95TtftSeconds}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-slo-margin" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">SLO Margin</span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Extra tolerance above the target TTFT, expressed as a ratio such as 0.1 for 10%.
              </p>
            </label>
            <input
              aria-label="SLO Margin"
              id="cost-latency-slo-margin"
              name="cost_latency_slo_margin"
              type="number"
              step="0.01"
              min="0"
              defaultValue={sloMargin}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-min-samples-for-strict-slo" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Min Samples For Strict SLO
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Number of observed requests required before strict SLO pass filtering is applied.
              </p>
            </label>
            <input
              aria-label="Min Samples For Strict SLO"
              id="cost-latency-min-samples-for-strict-slo"
              name="cost_latency_min_samples_for_strict_slo"
              type="number"
              step="1"
              min="1"
              defaultValue={minSamplesForStrictSlo}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-cold-start-floor" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Cold Start Floor
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Minimum samples each deployment should receive before normal SLO scoring resumes.
              </p>
            </label>
            <input
              aria-label="Cold Start Floor"
              id="cost-latency-cold-start-floor"
              name="cost_latency_cold_start_floor"
              type="number"
              step="1"
              min="0"
              defaultValue={coldStartFloor}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-cold-start-exposure-interval" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Cold Start Exposure Interval
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Force periodic exposure of cold-start deployments every N selections so they can accumulate latency samples.
              </p>
            </label>
            <input
              aria-label="Cold Start Exposure Interval"
              id="cost-latency-cold-start-exposure-interval"
              name="cost_latency_cold_start_exposure_interval"
              type="number"
              step="1"
              min="1"
              defaultValue={coldStartExposureInterval}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-max-timeout-rate-for-slo-pass" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Max Timeout Rate For SLO Pass
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Reliability gate for timeout rate when deciding whether a deployment still counts as SLO-pass.
              </p>
            </label>
            <input
              aria-label="Max Timeout Rate For SLO Pass"
              id="cost-latency-max-timeout-rate-for-slo-pass"
              name="cost_latency_max_timeout_rate_for_slo_pass"
              type="number"
              step="0.01"
              min="0"
              defaultValue={maxTimeoutRateForSloPass ?? ""}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="cost-latency-max-5xx-rate-for-slo-pass" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Max 5xx Rate For SLO Pass
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                Reliability gate for 5xx rate when deciding whether a deployment still counts as SLO-pass.
              </p>
            </label>
            <input
              aria-label="Max 5xx Rate For SLO Pass"
              id="cost-latency-max-5xx-rate-for-slo-pass"
              name="cost_latency_max_5xx_rate_for_slo_pass"
              type="number"
              step="0.01"
              min="0"
              defaultValue={max5xxRateForSloPass ?? ""}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900"
            />
          </div>

          <div className="space-y-2 lg:col-span-2">
            <label htmlFor="cost-latency-per-model-group-routing" className="block">
              <span className="text-xs font-medium text-gray-700 uppercase tracking-wide">
                Per-Model-Group Routing
              </span>
              <p className="text-xs text-gray-500 mt-0.5 mb-2">
                JSON map of model group to routing mode, for example{" "}
                <code>{'{"ai-seek-fast-small":"cost-first"}'}</code>.
              </p>
            </label>
            <textarea
              aria-label="Per-Model-Group Routing"
              id="cost-latency-per-model-group-routing"
              name="cost_latency_per_model_group_routing"
              defaultValue={JSON.stringify(perModelGroupRouting, null, 2)}
              rows={8}
              className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-gray-900"
            />
          </div>
        </div>
      </div>

      <div className="border-t border-gray-200" />
    </>
  );
};

export default CostLatencyBalancedConfiguration;
