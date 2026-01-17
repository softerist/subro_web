/** @vitest-environment jsdom */
import {
  render,
  screen,
  waitFor,
  cleanup,
  fireEvent,
  act,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);
import { PasswordSettings } from "@/features/auth/components/PasswordSettings";
import { api } from "@/lib/apiClient";

// Mock API
vi.mock("@/lib/apiClient", () => ({
  api: {
    patch: vi.fn(),
  },
}));

// Mock Lucide icons
vi.mock("lucide-react", () => ({
  Key: () => <div data-testid="icon-key" />,
  Loader2: () => <div data-testid="icon-loader" />,
  CheckCircle: () => <div data-testid="icon-check-circle" />,
  AlertCircle: () => <div data-testid="icon-alert-circle" />,
  Eye: () => <div data-testid="icon-eye" />,
  EyeOff: () => <div data-testid="icon-eye-off" />,
}));

// Mock React Query (Use a wrapper or mock useMutation)
// Since the component uses useMutation from @tanstack/react-query, we need a wrapper
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

describe("PasswordSettings", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <PasswordSettings />
      </QueryClientProvider>,
    );

  it("renders the password change form", () => {
    renderComponent();
    expect(
      screen.getByRole("heading", { name: "Change Password" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Change Password" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Current Password")).toBeInTheDocument();
    expect(screen.getByLabelText("New Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm New Password")).toBeInTheDocument();
  });

  it("shows error if passwords do not match", async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.type(screen.getByLabelText("Current Password"), "oldPass123");
    await user.type(screen.getByLabelText("New Password"), "NewPass123!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "Mismatch123!",
    );
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(screen.getByText("New passwords do not match.")).toBeInTheDocument();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("shows error if password is too short", async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.type(screen.getByLabelText("New Password"), "Short1!");
    await user.type(screen.getByLabelText("Confirm New Password"), "Short1!");
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(
      screen.getByText("Password must be at least 8 characters long."),
    ).toBeInTheDocument();
  });

  it("shows error if password missing uppercase", async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.type(screen.getByLabelText("New Password"), "lowercase123!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "lowercase123!",
    );
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(
      screen.getByText("Password must contain at least one uppercase letter."),
    ).toBeInTheDocument();
  });

  it("shows error if password missing lowercase", async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.type(screen.getByLabelText("New Password"), "ALLCAPS123!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "ALLCAPS123!",
    );
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(
      screen.getByText("Password must contain at least one lowercase letter."),
    ).toBeInTheDocument();
  });

  it("shows error if password missing number", async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.type(screen.getByLabelText("New Password"), "NoNumberPass!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "NoNumberPass!",
    );
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(
      screen.getByText("Password must contain at least one number."),
    ).toBeInTheDocument();
  });

  it("submits form when validation passes", async () => {
    const user = userEvent.setup();
    renderComponent();

    vi.mocked(api.patch).mockResolvedValue({ data: { success: true } });

    await user.type(screen.getByLabelText("Current Password"), "OldPass123");
    await user.type(screen.getByLabelText("New Password"), "NewPass123!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "NewPass123!",
    );

    const submitBtn = screen.getByRole("button", { name: "Change Password" });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith("/v1/auth/password", {
        current_password: "OldPass123",
        new_password: "NewPass123!",
      });
    });

    await waitFor(() => {
      expect(
        screen.getByText("Password changed successfully!"),
      ).toBeInTheDocument();
    });

    // Verify form cleared
    expect(screen.getByLabelText("Current Password")).toHaveValue("");
  });

  it("shows API error when change password fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.patch).mockRejectedValue({
      response: { data: { detail: "Server error" } },
    });
    renderComponent();

    await user.type(screen.getByLabelText("Current Password"), "OldPass123");
    await user.type(screen.getByLabelText("New Password"), "NewPass123!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "NewPass123!",
    );
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(await screen.findByText("Server error")).toBeInTheDocument();
  });

  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    renderComponent();

    const newPassInput = screen.getByLabelText("New Password");
    expect(newPassInput).toHaveAttribute("type", "password");

    // Find the toggle button associated with new password
    // The component renders 3 inputs, each with a toggle button next to it.
    // We need to find the specific button.

    // Approach: The button is the next sibling or closer wrapper in the DOM structure.
    // Or we can get all buttons with eye icons.
    const eyeIcons = screen.getAllByTestId("icon-eye");
    // Assuming they are in order: current, new, confirm
    const toggleNewPassBtn = eyeIcons[1].closest("button");

    if (toggleNewPassBtn) {
      await user.click(toggleNewPassBtn);
      expect(newPassInput).toHaveAttribute("type", "text");

      await user.click(toggleNewPassBtn);
      expect(newPassInput).toHaveAttribute("type", "password");
    }
  });

  it("toggles visibility for current and confirm password fields", async () => {
    const user = userEvent.setup();
    renderComponent();

    const currentInput = screen.getByLabelText("Current Password");
    const confirmInput = screen.getByLabelText("Confirm New Password");

    const eyeIcons = screen.getAllByTestId("icon-eye");
    const currentToggle = eyeIcons[0].closest("button");
    const confirmToggle = eyeIcons[2].closest("button");

    expect(currentInput).toHaveAttribute("type", "password");
    expect(confirmInput).toHaveAttribute("type", "password");

    if (currentToggle) {
      await user.click(currentToggle);
      expect(currentInput).toHaveAttribute("type", "text");
    }

    if (confirmToggle) {
      await user.click(confirmToggle);
      expect(confirmInput).toHaveAttribute("type", "text");
    }
  });

  it("clears success message after timeout", async () => {
    vi.useRealTimers(); // Ensure real timers
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    renderComponent();

    vi.mocked(api.patch).mockResolvedValue({ data: { success: true } });

    fireEvent.change(screen.getByLabelText("Current Password"), {
      target: { value: "OldPass123" },
    });
    fireEvent.change(screen.getByLabelText("New Password"), {
      target: { value: "NewPass123!" },
    });
    fireEvent.change(screen.getByLabelText("Confirm New Password"), {
      target: { value: "NewPass123!" },
    });

    const form = screen
      .getByRole("button", { name: "Change Password" })
      .closest("form");
    if (!form) throw new Error("Form not found");
    fireEvent.submit(form);

    // Wait for success message
    await screen.findByText("Password changed successfully!");

    // Verify setTimeout was called with 5000
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 5000);

    // Manually run the callback
    const callback = setTimeoutSpy.mock.calls.find(
      (call) => call[1] === 5000,
    )?.[0] as Function;
    expect(callback).toBeDefined();

    await act(async () => {
      callback();
    });

    // Verify message is gone
    await waitFor(() => {
      expect(
        screen.queryByText("Password changed successfully!"),
      ).not.toBeInTheDocument();
    });
  });

  it("shows fallback error message when detail is missing", async () => {
    const user = userEvent.setup();
    vi.mocked(api.patch).mockRejectedValue(new Error("Generic error")); // Use an error object
    renderComponent();

    await user.type(screen.getByLabelText("Current Password"), "OldPass123");
    await user.type(screen.getByLabelText("New Password"), "NewPass123!");
    await user.type(
      screen.getByLabelText("Confirm New Password"),
      "NewPass123!",
    );
    await user.click(screen.getByRole("button", { name: "Change Password" }));

    expect(
      await screen.findByText("Failed to change password"),
    ).toBeInTheDocument();
  });
});
