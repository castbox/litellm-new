import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders, screen, waitFor } from "../../../tests/test-utils";
import NotificationsManager from "../molecules/notifications_manager";
import { getCallbacksCall, getRouterSettingsCall, setCallbacksCall } from "../networking";
import RouterSettings from "./index";

vi.mock("antd", () => ({
  Select: Object.assign(
    ({ value, onChange, children }: any) => (
      <select
        data-testid="strategy-select"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {children}
      </select>
    ),
    {
      Option: ({ value, children }: any) => (
        <option value={value}>{children}</option>
      ),
    }
  ),
}));

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

const mockCallbacksResponse = {
  router_settings: {
    routing_strategy: "simple-shuffle",
    custom_routing_strategy: "cost-latency-balanced",
    custom_routing_strategy_args: {
      default_routing_mode: "balanced",
      target_p95_ttft_seconds: 5,
      slo_margin: 0.1,
      min_samples_for_strict_slo: 30,
      cold_start_floor: 5,
      cold_start_exposure_interval: 20,
      max_timeout_rate_for_slo_pass: 0.02,
      max_5xx_rate_for_slo_pass: 0.06,
      per_model_group_routing: {
        "ai-seek-fast-small": "cost-first",
      },
    },
    num_retries: 3,
    timeout: 30,
  },
};

const mockRouterSettingsResponse = {
  fields: [
    {
      field_name: "routing_strategy",
      ui_field_name: "Routing Strategy",
      field_description: "How requests are distributed",
      options: ["simple-shuffle", "latency-based-routing", "cost-latency-balanced"],
      link: null,
    },
    {
      field_name: "custom_routing_strategy",
      ui_field_name: "Custom Routing Strategy",
      field_description: "Optional custom routing strategy layered on top of the built-in router strategy.",
      options: ["cost-latency-balanced"],
      link: null,
    },
    {
      field_name: "enable_tag_filtering",
      ui_field_name: "Tag Filtering",
      field_description: "Route by tag",
      field_value: false,
      link: null,
    },
  ],
  routing_strategy_descriptions: {
    "simple-shuffle": "Randomly pick a deployment",
    "latency-based-routing": "Pick the lowest-latency deployment",
    "cost-latency-balanced": "Balance cost, latency, and load while honoring SLOs.",
  },
};

const defaultProps = {
  accessToken: "test-token",
  userRole: "Admin",
  userID: "user-1",
  modelData: null,
};

describe("RouterSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getCallbacksCall).mockResolvedValue(mockCallbacksResponse);
    vi.mocked(getRouterSettingsCall).mockResolvedValue(mockRouterSettingsResponse);
    vi.mocked(setCallbacksCall).mockResolvedValue({});
  });

  it("should render nothing when accessToken is null", () => {
    const { container } = renderWithProviders(
      <RouterSettings {...defaultProps} accessToken={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("should render the Save Changes and Reset buttons when authenticated", () => {
    renderWithProviders(<RouterSettings {...defaultProps} />);
    expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();
  });

  it("should fetch callbacks and router settings on mount", async () => {
    renderWithProviders(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(getCallbacksCall).toHaveBeenCalledWith("test-token", "user-1", "Admin");
    });
    expect(getRouterSettingsCall).toHaveBeenCalledWith("test-token");
  });

  it("should not fetch data when any required prop is missing", () => {
    renderWithProviders(<RouterSettings {...defaultProps} userRole={null} />);
    expect(getCallbacksCall).not.toHaveBeenCalled();
  });

  it("should render routing strategies loaded from the API", async () => {
    renderWithProviders(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("strategy-select")).toBeInTheDocument();
    });

    const select = screen.getByTestId("strategy-select") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((option) => option.value);
    expect(optionValues).toContain("simple-shuffle");
    expect(optionValues).toContain("latency-based-routing");
    expect(optionValues).toContain("cost-latency-balanced");
  });

  it("should render cost-latency-balanced configuration when the custom strategy is active", async () => {
    renderWithProviders(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("Cost-Latency Balanced Configuration")).toBeInTheDocument();
    });

    expect(screen.getByLabelText("Default Routing Mode")).toHaveValue("balanced");
    expect(screen.getByLabelText("Target P95 TTFT (seconds)")).toHaveValue(5);
    expect(screen.getByLabelText("SLO Margin")).toHaveValue(0.1);
    expect(screen.getByLabelText("Min Samples For Strict SLO")).toHaveValue(30);
    expect(screen.getByLabelText("Cold Start Floor")).toHaveValue(5);
    expect(screen.getByLabelText("Cold Start Exposure Interval")).toHaveValue(20);
    expect(screen.getByLabelText("Max Timeout Rate For SLO Pass")).toHaveValue(0.02);
    expect(screen.getByLabelText("Max 5xx Rate For SLO Pass")).toHaveValue(0.06);
    expect(screen.getByLabelText("Per-Model-Group Routing")).toHaveValue(
      '{\n  "ai-seek-fast-small": "cost-first"\n}'
    );
  });

  it("should call setCallbacksCall with custom strategy settings on Save Changes", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("strategy-select")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(setCallbacksCall).toHaveBeenCalledWith(
      "test-token",
      expect.objectContaining({
        router_settings: expect.objectContaining({
          routing_strategy: "simple-shuffle",
          custom_routing_strategy: "cost-latency-balanced",
          custom_routing_strategy_args: expect.objectContaining({
            default_routing_mode: "balanced",
            target_p95_ttft_seconds: 5,
            slo_margin: 0.1,
            min_samples_for_strict_slo: 30,
            cold_start_floor: 5,
            cold_start_exposure_interval: 20,
            max_timeout_rate_for_slo_pass: 0.02,
            max_5xx_rate_for_slo_pass: 0.06,
          }),
        }),
      })
    );
  });

  it("should show a success notification after saving", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RouterSettings {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("strategy-select")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(NotificationsManager.success).toHaveBeenCalledWith(
      "router settings updated successfully"
    );
  });

  it("should submit cost-latency-balanced SLO settings in custom routing strategy args", async () => {
    renderWithProviders(<RouterSettings {...defaultProps} />);

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
    fireEvent.change(screen.getByLabelText("Cold Start Floor"), {
      target: { value: "4" },
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

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(setCallbacksCall).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({
          router_settings: expect.objectContaining({
            custom_routing_strategy: "cost-latency-balanced",
            custom_routing_strategy_args: {
              default_routing_mode: "latency-first",
              target_p95_ttft_seconds: 4.5,
              slo_margin: 0.2,
              min_samples_for_strict_slo: 12,
              cold_start_floor: 4,
              cold_start_exposure_interval: 7,
              max_timeout_rate_for_slo_pass: 0.08,
              max_5xx_rate_for_slo_pass: 0.15,
              per_model_group_routing: {
                "strategy-balanced-test2": "balanced",
              },
            },
          }),
        })
      );
    });
  });
});
