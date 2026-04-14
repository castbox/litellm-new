import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RouterSettings from ".";
import { getCallbacksCall, getRouterSettingsCall, setCallbacksCall } from "../networking";

vi.mock("../networking", () => ({
  getCallbacksCall: vi.fn(),
  getRouterSettingsCall: vi.fn(),
  setCallbacksCall: vi.fn(),
}));

vi.mock("../molecules/notifications_manager", () => ({
  __esModule: true,
  default: {
    success: vi.fn(),
    fromBackend: vi.fn(),
  },
}));

describe("RouterSettings", () => {
  const defaultProps = {
    accessToken: "token",
    userRole: "admin",
    userID: "user-123",
    modelData: { data: [] },
  };

  const mockGetCallbacksCall = vi.mocked(getCallbacksCall);
  const mockGetRouterSettingsCall = vi.mocked(getRouterSettingsCall);
  const mockSetCallbacksCall = vi.mocked(setCallbacksCall);

  beforeEach(() => {
    vi.clearAllMocks();

    mockGetCallbacksCall.mockResolvedValue({
      router_settings: {
        routing_strategy: "simple-shuffle",
        custom_routing_strategy: "cost-latency-balanced",
        custom_routing_strategy_args: {
          default_routing_mode: "balanced",
          target_p95_ttft_seconds: 5,
          slo_margin: 0.1,
          min_samples_for_strict_slo: 30,
          cold_start_exposure_interval: 20,
          max_timeout_rate_for_slo_pass: 0.02,
          max_5xx_rate_for_slo_pass: 0.06,
          per_model_group_routing: {
            "ai-seek-fast-small": "cost-first",
          },
        },
      },
    });

    mockSetCallbacksCall.mockResolvedValue({});

    mockGetRouterSettingsCall.mockResolvedValue({
      fields: [
        {
          field_name: "routing_strategy",
          ui_field_name: "Routing Strategy",
          field_description: "Routing strategy to use for load balancing across deployments",
          options: ["simple-shuffle", "least-busy", "cost-latency-balanced"],
        },
        {
          field_name: "custom_routing_strategy",
          ui_field_name: "Custom Routing Strategy",
          field_description: "Optional custom routing strategy layered on top of the built-in router strategy.",
          options: ["cost-latency-balanced"],
        },
        {
          field_name: "enable_tag_filtering",
          ui_field_name: "Enable Tag Filtering",
          field_description: "Enable tag-based routing",
          field_value: false,
        },
      ],
      routing_strategy_descriptions: {
        "simple-shuffle": "Randomly picks a deployment from the list. Simple and fast.",
        "cost-latency-balanced":
          "Balances cost, latency, and load while honoring SLO and reliability signals.",
      },
    });
  });

  it("renders cost-latency-balanced configuration when the custom strategy is active", async () => {
    render(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Cost-Latency Balanced Configuration")).toBeInTheDocument();
      expect(screen.getByLabelText("Default Routing Mode")).toHaveValue("balanced");
      expect(screen.getByLabelText("Target P95 TTFT (seconds)")).toHaveValue(5);
      expect(screen.getByLabelText("SLO Margin")).toHaveValue(0.1);
      expect(screen.getByLabelText("Min Samples For Strict SLO")).toHaveValue(30);
      expect(screen.getByLabelText("Cold Start Exposure Interval")).toHaveValue(20);
      expect(screen.getByLabelText("Max Timeout Rate For SLO Pass")).toHaveValue(0.02);
      expect(screen.getByLabelText("Max 5xx Rate For SLO Pass")).toHaveValue(0.06);
      expect(screen.getByLabelText("Per-Model-Group Routing")).toHaveValue(
        '{\n  "ai-seek-fast-small": "cost-first"\n}',
      );
    });
  });

  it("submits cost-latency-balanced SLO settings in custom routing strategy args", async () => {
    render(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Cost-Latency Balanced Configuration")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Target P95 TTFT (seconds)"), {
      target: { value: "4.5" },
    });
    fireEvent.change(screen.getByLabelText("SLO Margin"), {
      target: { value: "0.2" },
    });
    fireEvent.change(screen.getByLabelText("Min Samples For Strict SLO"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText("Cold Start Exposure Interval"), {
      target: { value: "7" },
    });
    fireEvent.change(screen.getByLabelText("Max Timeout Rate For SLO Pass"), {
      target: { value: "0.08" },
    });
    fireEvent.change(screen.getByLabelText("Max 5xx Rate For SLO Pass"), {
      target: { value: "0.15" },
    });
    fireEvent.change(screen.getByLabelText("Default Routing Mode"), {
      target: { value: "latency-first" },
    });
    fireEvent.change(screen.getByLabelText("Per-Model-Group Routing"), {
      target: { value: '{\n  "strategy-balanced-test2": "balanced"\n}' },
    });

    fireEvent.click(screen.getByText("Save Changes"));

    await waitFor(() => {
      expect(mockSetCallbacksCall).toHaveBeenCalledWith("token", {
        router_settings: expect.objectContaining({
          custom_routing_strategy: "cost-latency-balanced",
          custom_routing_strategy_args: {
            default_routing_mode: "latency-first",
            target_p95_ttft_seconds: 4.5,
            slo_margin: 0.2,
            min_samples_for_strict_slo: 12,
            cold_start_exposure_interval: 7,
            max_timeout_rate_for_slo_pass: 0.08,
            max_5xx_rate_for_slo_pass: 0.15,
            per_model_group_routing: {
              "strategy-balanced-test2": "balanced",
            },
          },
        }),
      });
    });
  });
});
