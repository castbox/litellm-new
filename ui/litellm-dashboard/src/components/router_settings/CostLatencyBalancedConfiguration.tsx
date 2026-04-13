import React from "react";

interface CostLatencyBalancedConfigurationProps {
  customRoutingStrategyArgs?: {
    default_routing_mode?: string;
    per_model_group_routing?: Record<string, string>;
  };
}

const CostLatencyBalancedConfiguration: React.FC<CostLatencyBalancedConfigurationProps> = ({
  customRoutingStrategyArgs,
}) => {
  const defaultRoutingMode = customRoutingStrategyArgs?.default_routing_mode || "balanced";
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
