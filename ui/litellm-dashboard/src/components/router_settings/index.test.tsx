import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RouterSettings from ".";
import { getCallbacksCall, getRouterSettingsCall } from "../networking";

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

  beforeEach(() => {
    vi.clearAllMocks();

    mockGetCallbacksCall.mockResolvedValue({
      router_settings: {
        routing_strategy: "simple-shuffle",
        custom_routing_strategy: "cost-latency-balanced",
        custom_routing_strategy_args: {
          default_routing_mode: "balanced",
          per_model_group_routing: {
            "ai-seek-fast-small": "cost-first",
          },
        },
      },
    });

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
      expect(screen.getByLabelText("Per-Model-Group Routing")).toHaveValue(
        '{\n  "ai-seek-fast-small": "cost-first"\n}',
      );
    });
  });
});
