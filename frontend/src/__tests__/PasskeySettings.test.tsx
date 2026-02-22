// frontend/src/__tests__/PasskeySettings.test.tsx
/**
 * Tests for PasskeySettings component
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { PasskeySettings } from "@/features/auth/components/PasskeySettings";
import * as passkeyApi from "@/features/auth/api/passkey";

// Mock the passkey API
vi.mock("@/features/auth/api/passkey");

// Mock auth store
const mockUser = {
  id: "user-123",
  email: "test@example.com",
  role: "user" as const,
};
vi.mock("@/store/authStore", () => ({
  useAuthStore: vi.fn((selector) => {
    const state = {
      user: mockUser,
      accessToken: "test-token",
      isAuthenticated: true,
    };
    return selector ? selector(state) : state;
  }),
}));

// Helper to wrap component with providers
const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>{component}</QueryClientProvider>,
  );
};

describe("PasskeySettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows message when WebAuthn is not supported", () => {
    // Mock WebAuthn not supported
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(false);

    renderWithProviders(<PasskeySettings />);

    expect(
      screen.getByText(/Your browser doesn't support passkeys/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Add Passkey")).not.toBeInTheDocument();
  });

  it("shows loading state while fetching passkeys", () => {
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockImplementation(
      () => new Promise(() => {}), // Never resolves
    );

    renderWithProviders(<PasskeySettings />);

    expect(
      screen.getByRole("progressbar", { hidden: true }),
    ).toBeInTheDocument();
  });

  it("shows empty state with info banner when no passkeys exist", async () => {
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(
        screen.getByText(/Enable passwordless login/i),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Add Passkey")).toBeInTheDocument();
  });

  it("handles undefined passkeys array gracefully", async () => {
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: undefined as any, // Simulating undefined passkeys from API
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(
        screen.getByText(/Enable passwordless login/i),
      ).toBeInTheDocument();
    });

    expect(screen.getByText("Add Passkey")).toBeInTheDocument();
  });

  it("displays list of passkeys", async () => {
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 2,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "MacBook Touch ID",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: "2026-01-15T00:00:00Z",
          backup_eligible: true,
          backup_state: true,
        },
        {
          id: "passkey-2",
          device_name: "iPhone Face ID",
          created_at: "2026-01-10T00:00:00Z",
          last_used_at: null,
          backup_eligible: true,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("MacBook Touch ID")).toBeInTheDocument();
    });

    expect(screen.getByText("iPhone Face ID")).toBeInTheDocument();
    expect(screen.getByText(/Synced/i)).toBeInTheDocument(); // First passkey is synced
  });

  it("opens registration dialog when Add Passkey clicked", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));

    expect(screen.getByText("Add a Passkey")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Default:/i)).toBeInTheDocument();
  });

  it("successfully registers a new passkey", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys")
      .mockResolvedValueOnce({ passkey_count: 0, passkeys: [] })
      .mockResolvedValueOnce({
        passkey_count: 1,
        passkeys: [
          {
            id: "new-passkey",
            device_name: "My Passkey",
            created_at: "2026-01-18T00:00:00Z",
            last_used_at: null,
            backup_eligible: false,
            backup_state: false,
          },
        ],
      });

    vi.spyOn(passkeyApi.passkeyApi, "register").mockResolvedValue({
      id: "new-passkey",
      device_name: "My Passkey",
      created_at: "2026-01-18T00:00:00Z",
      last_used_at: null,
      backup_eligible: false,
      backup_state: false,
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    // Open dialog
    await user.click(screen.getByText("Add Passkey"));

    // Enter device name
    const nameInput = screen.getByPlaceholderText(/Default:/i);
    await user.type(nameInput, "My Passkey");

    // Click Continue
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    // Wait for registration to complete
    await waitFor(() => {
      expect(passkeyApi.passkeyApi.register).toHaveBeenCalledWith("My Passkey");
    });

    // Dialog should close and new passkey appears
    await waitFor(() => {
      expect(screen.queryByText("Add a Passkey")).not.toBeInTheDocument();
    });
  });

  it("shows error when passkey registration fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue({
      response: { data: { detail: "Registration failed" } },
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(screen.getByText("Registration failed")).toBeInTheDocument();
    });
  });

  it("closes register dialog when cancel is clicked", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    // Open dialog
    await user.click(screen.getByText("Add Passkey"));

    // Verify dialog is open
    expect(screen.getByText("Add a Passkey")).toBeInTheDocument();

    // Type something in device name
    const nameInput = screen.getByPlaceholderText(/Default:/i);
    await user.type(nameInput, "My Device");

    // Click Cancel button
    await user.click(screen.getByRole("button", { name: /Cancel/i }));

    // Dialog should close and state should be reset
    await waitFor(() => {
      expect(screen.queryByText("Add a Passkey")).not.toBeInTheDocument();
    });
  });

  it("allows renaming a passkey", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Old Name",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    vi.spyOn(passkeyApi.passkeyApi, "renamePasskey").mockResolvedValue();

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Old Name")).toBeInTheDocument();
    });

    // Click edit button
    const editButtons = screen.getAllByRole("button", { name: "" });
    const editButton = editButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-pencil"]'),
    );
    await user.click(editButton!);

    // Input field should appear
    const nameInput = screen.getByDisplayValue("Old Name");
    await user.clear(nameInput);
    await user.type(nameInput, "New Name");

    // Click save (check icon)
    const saveButton = screen
      .getAllByRole("button", { name: "" })
      .find((btn) => btn.querySelector('svg[class*="lucide-check"]'));
    await user.click(saveButton!);

    await waitFor(() => {
      expect(passkeyApi.passkeyApi.renamePasskey).toHaveBeenCalledWith(
        "passkey-1",
        "New Name",
      );
    });
  });

  it("cancels edit mode when clicking cancel button", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Test Passkey",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Test Passkey")).toBeInTheDocument();
    });

    // Click edit button
    const editButtons = screen.getAllByRole("button", { name: "" });
    const editButton = editButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-pencil"]'),
    );
    await user.click(editButton!);

    // Input field should appear
    expect(screen.getByDisplayValue("Test Passkey")).toBeInTheDocument();

    // Click cancel button (X icon)
    const cancelButton = screen
      .getAllByRole("button", { name: "" })
      .find((btn) => btn.querySelector('svg[class*="lucide-x"]'));
    await user.click(cancelButton!);

    // Should exit edit mode and show original name
    await waitFor(() => {
      expect(
        screen.queryByDisplayValue("Test Passkey"),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("Test Passkey")).toBeInTheDocument();
  });

  it("displays 'Passkey' when device_name is null", async () => {
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: null,
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Passkey")).toBeInTheDocument();
    });
  });

  it("displays 'Unknown' when created_at is null", async () => {
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Test",
          created_at: null,
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText(/Unknown/)).toBeInTheDocument();
    });
  });

  it("saves rename on Enter key press", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Old Name",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    vi.spyOn(passkeyApi.passkeyApi, "renamePasskey").mockResolvedValue();

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Old Name")).toBeInTheDocument();
    });

    // Click edit button
    const editButtons = screen.getAllByRole("button", { name: "" });
    const editButton = editButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-pencil"]'),
    );
    await user.click(editButton!);

    // Clear and type new name
    const nameInput = screen.getByDisplayValue("Old Name");
    await user.clear(nameInput);
    await user.type(nameInput, "New Name{Enter}");

    await waitFor(() => {
      expect(passkeyApi.passkeyApi.renamePasskey).toHaveBeenCalledWith(
        "passkey-1",
        "New Name",
      );
    });
  });

  it("cancels edit on Escape key press", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Test Passkey",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Test Passkey")).toBeInTheDocument();
    });

    // Click edit button
    const editButtons = screen.getAllByRole("button", { name: "" });
    const editButton = editButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-pencil"]'),
    );
    await user.click(editButton!);

    // Press Escape
    const nameInput = screen.getByDisplayValue("Test Passkey");
    await user.type(nameInput, "{Escape}");

    // Should exit edit mode
    await waitFor(() => {
      expect(
        screen.queryByDisplayValue("Test Passkey"),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("Test Passkey")).toBeInTheDocument();
  });

  it("does not save when edit name is empty", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Test Passkey",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    vi.spyOn(passkeyApi.passkeyApi, "renamePasskey").mockResolvedValue();

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Test Passkey")).toBeInTheDocument();
    });

    // Click edit button
    const editButtons = screen.getAllByRole("button", { name: "" });
    const editButton = editButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-pencil"]'),
    );
    await user.click(editButton!);

    // Clear input and try to save with empty value
    const nameInput = screen.getByDisplayValue("Test Passkey");
    await user.clear(nameInput);

    // Click save button
    const saveButton = screen
      .getAllByRole("button", { name: "" })
      .find((btn) => btn.querySelector('svg[class*="lucide-check"]'));
    await user.click(saveButton!);

    // Should NOT call rename with empty name
    expect(passkeyApi.passkeyApi.renamePasskey).not.toHaveBeenCalled();
  });

  it("shows fallback error message when registration fails without detail", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue({
      message: "Network error",
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  it("shows default error message when registration fails without any message", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue({});

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(
        screen.getByText("An error occurred. Please try again."),
      ).toBeInTheDocument();
    });
  });

  it("maps known error name (NotAllowedError) to user-friendly message", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    // Error with known name (covers errorName branch at line 141)
    const error = new Error("User cancelled");
    error.name = "NotAllowedError";
    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue(error);

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(
        screen.getByText(
          "Registration cancelled or not permitted by your browser",
        ),
      ).toBeInTheDocument();
    });
  });

  it("maps error code from response to user-friendly message", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    // Error with code in response (covers errorCode branch at line 142)
    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue({
      response: { data: { code: "challenge_expired" } },
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Session expired. Please start again."),
      ).toBeInTheDocument();
    });
  });

  it("extracts message from nested detail object", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    // Error with nested detail object (covers typeof data?.detail === 'object' branch at line 143)
    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue({
      response: {
        data: {
          detail: {
            code: "unknown_code",
            message: "Custom nested error message",
          },
        },
      },
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Custom nested error message"),
      ).toBeInTheDocument();
    });
  });

  it("extracts code from nested detail object for known error codes", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    // Error with nested detail.code (covers errorCode from nested detail)
    vi.spyOn(passkeyApi.passkeyApi, "register").mockRejectedValue({
      response: {
        data: {
          detail: {
            code: "REAUTH_REQUIRED",
          },
        },
      },
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Add Passkey"));
    await user.click(screen.getByRole("button", { name: /Continue/i }));

    await waitFor(() => {
      expect(
        screen.getByText("Please verify your identity to continue"),
      ).toBeInTheDocument();
    });
  });

  it("handles passkey with null device_name in edit mode", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: null,
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Passkey")).toBeInTheDocument();
    });

    // Click edit button - device_name is null so input should be empty
    const editButtons = screen.getAllByRole("button", { name: "" });
    const editButton = editButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-pencil"]'),
    );
    await user.click(editButton!);

    // Input should have empty value since device_name was null
    const nameInput = screen.getByRole("textbox");
    expect(nameInput).toHaveValue("");
  });

  it("allows deleting a passkey", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys")
      .mockResolvedValueOnce({
        passkey_count: 1,
        passkeys: [
          {
            id: "passkey-1",
            device_name: "Test Passkey",
            created_at: "2026-01-01T00:00:00Z",
            last_used_at: null,
            backup_eligible: false,
            backup_state: false,
          },
        ],
      })
      .mockResolvedValueOnce({ passkey_count: 0, passkeys: [] });

    vi.spyOn(passkeyApi.passkeyApi, "deletePasskey").mockResolvedValue();

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Test Passkey")).toBeInTheDocument();
    });

    // Click delete button
    const deleteButtons = screen.getAllByRole("button", { name: "" });
    const deleteButton = deleteButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-trash"]'),
    );
    await user.click(deleteButton!);

    // Confirmation dialog appears
    await waitFor(() => {
      expect(screen.getByText("Delete Passkey?")).toBeInTheDocument();
    });

    // Click delete in dialog
    const confirmButton = screen.getByRole("button", { name: /Delete/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(passkeyApi.passkeyApi.deletePasskey).toHaveBeenCalledWith(
        "passkey-1",
        expect.anything(),
      );
    });
  });

  it("cancels delete when user clicks Cancel", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Test Passkey",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    vi.spyOn(passkeyApi.passkeyApi, "deletePasskey").mockResolvedValue();

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Test Passkey")).toBeInTheDocument();
    });

    // Click delete button
    const deleteButtons = screen.getAllByRole("button", { name: "" });
    const deleteButton = deleteButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-trash"]'),
    );
    await user.click(deleteButton!);

    // Click Cancel
    const cancelButton = screen.getByRole("button", { name: /Cancel/i });
    await user.click(cancelButton);

    // Dialog should close, passkey not deleted
    await waitFor(() => {
      expect(screen.queryByText("Delete Passkey?")).not.toBeInTheDocument();
    });
    expect(passkeyApi.passkeyApi.deletePasskey).not.toHaveBeenCalled();
  });

  it("closes delete dialog when clicking outside (onOpenChange)", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 1,
      passkeys: [
        {
          id: "passkey-1",
          device_name: "Test Passkey",
          created_at: "2026-01-01T00:00:00Z",
          last_used_at: null,
          backup_eligible: false,
          backup_state: false,
        },
      ],
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Test Passkey")).toBeInTheDocument();
    });

    // Click delete button to open dialog
    const deleteButtons = screen.getAllByRole("button", { name: "" });
    const deleteButton = deleteButtons.find((btn) =>
      btn.querySelector('svg[class*="lucide-trash"]'),
    );
    await user.click(deleteButton!);

    // Dialog should be open
    await waitFor(() => {
      expect(screen.getByText("Delete Passkey?")).toBeInTheDocument();
    });

    // Press Escape to close the dialog (triggers onOpenChange with false)
    await user.keyboard("{Escape}");

    // Dialog should close
    await waitFor(() => {
      expect(screen.queryByText("Delete Passkey?")).not.toBeInTheDocument();
    });
    expect(passkeyApi.passkeyApi.deletePasskey).not.toHaveBeenCalled();
  });

  it("uses fallback passkey name when UAParser fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    // Mock UAParser to throw an error
    const originalNavigator = navigator.userAgent;
    Object.defineProperty(navigator, "userAgent", {
      get: () => {
        throw new Error("UAParser error");
      },
      configurable: true,
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    // Open dialog - should use fallback name with date
    await user.click(screen.getByText("Add Passkey"));

    // The placeholder should contain "Passkey" followed by a date
    expect(
      screen.getByPlaceholderText(/Default: "Passkey/i),
    ).toBeInTheDocument();

    // Restore original navigator
    Object.defineProperty(navigator, "userAgent", {
      get: () => originalNavigator,
      configurable: true,
    });
  });

  it("uses fallback device and browser names when UAParser returns undefined", async () => {
    const user = userEvent.setup();
    vi.spyOn(passkeyApi, "isWebAuthnSupported").mockReturnValue(true);
    vi.spyOn(passkeyApi.passkeyApi, "listPasskeys").mockResolvedValue({
      passkey_count: 0,
      passkeys: [],
    });

    // Save original userAgent
    const originalUserAgent = navigator.userAgent;

    // Set userAgent to an empty or unknown value that UAParser can't parse well
    // This should result in undefined os.name and browser.name
    Object.defineProperty(navigator, "userAgent", {
      get: () => "",
      configurable: true,
    });

    renderWithProviders(<PasskeySettings />);

    await waitFor(() => {
      expect(screen.getByText("Add Passkey")).toBeInTheDocument();
    });

    // Open dialog - should use "Device – Browser" as fallback when UAParser can't parse
    await user.click(screen.getByText("Add Passkey"));

    // The placeholder should contain "Device – Browser" (the fallback values)
    expect(
      screen.getByPlaceholderText(/Default: "Device – Browser"/i),
    ).toBeInTheDocument();

    // Restore original userAgent
    Object.defineProperty(navigator, "userAgent", {
      get: () => originalUserAgent,
      configurable: true,
    });
  });
});
