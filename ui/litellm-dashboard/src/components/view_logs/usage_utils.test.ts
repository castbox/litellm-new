import { describe, expect, it } from "vitest";
import { getCacheReadTokens } from "./usage_utils";

describe("getCacheReadTokens", () => {
  it("prefers normalized cache_read_input_tokens when available", () => {
    expect(
      getCacheReadTokens({
        metadata: {
          additional_usage_values: {
            cache_read_input_tokens: 42,
            prompt_tokens_details: { cached_tokens: 100 },
          },
          usage_object: {
            prompt_tokens_details: { cached_tokens: 200 },
          },
        },
      }),
    ).toBe(42);
  });

  it("falls back to additional_usage_values.prompt_tokens_details.cached_tokens", () => {
    expect(
      getCacheReadTokens({
        metadata: {
          additional_usage_values: {
            prompt_tokens_details: { cached_tokens: 755 },
          },
        },
      }),
    ).toBe(755);
  });

  it("falls back to usage_object.prompt_tokens_details.cached_tokens", () => {
    expect(
      getCacheReadTokens({
        metadata: {
          usage_object: {
            prompt_tokens_details: { cached_tokens: 755 },
          },
        },
      }),
    ).toBe(755);
  });
});
