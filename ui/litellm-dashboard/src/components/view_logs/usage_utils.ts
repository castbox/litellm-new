type UsageContainer = {
  metadata?: {
    additional_usage_values?: {
      cache_read_input_tokens?: number | null;
      prompt_tokens_details?: {
        cached_tokens?: number | null;
      } | null;
    } | null;
    usage_object?: {
      cache_read_input_tokens?: number | null;
      prompt_tokens_details?: {
        cached_tokens?: number | null;
      } | null;
    } | null;
  } | null;
};

const toDisplayNumber = (value: unknown): number => {
  const normalized = typeof value === "string" ? Number(value) : value;
  return typeof normalized === "number" && Number.isFinite(normalized)
    ? normalized
    : 0;
};

export const getCacheReadTokens = (log?: UsageContainer | null): number => {
  const additionalUsageValues = log?.metadata?.additional_usage_values;
  const usageObject = log?.metadata?.usage_object;

  return toDisplayNumber(
    additionalUsageValues?.cache_read_input_tokens ??
      additionalUsageValues?.prompt_tokens_details?.cached_tokens ??
      usageObject?.cache_read_input_tokens ??
      usageObject?.prompt_tokens_details?.cached_tokens ??
      0,
  );
};
