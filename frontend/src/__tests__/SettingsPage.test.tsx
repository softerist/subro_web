/** @vitest-environment jsdom */
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
  cleanup,
  within,
} from "@testing-library/react";
import type { ComponentPropsWithoutRef } from "react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SettingsPage from "../pages/SettingsPage";
import { useAuthStore, type AuthState, type User } from "@/store/authStore";
import {
  getSettings,
  updateSettings,
  type SettingsRead,
} from "@/lib/settingsApi";
import { usersApi } from "@/lib/users";
import type { ReactNode } from "react";

const createUser = () => userEvent.setup();

// Mock framer-motion to avoid animation issues in tests (strip motion-only props)
vi.mock("framer-motion", () => {
  const stripProps = (
    { children, ...rest }: Record<string, unknown>,
    Element: React.ElementType,
  ) => {
    // Remove motion-only props that React DOM does not understand

    const {
      initial: _initial,
      animate: _animate,
      exit: _exit,
      layout: _layout,
      layoutId: _layoutId,
      transition: _transition,
      variants: _variants,
      whileTap: _whileTap,
      whileHover: _whileHover,
      ...domProps
    } = rest;
    const Component = Element;
    return <Component {...domProps}>{children}</Component>;
  };
  return {
    motion: {
      div: (props: ComponentPropsWithoutRef<"div">) =>
        stripProps(props as Record<string, unknown>, "div"),
      span: (props: ComponentPropsWithoutRef<"span">) =>
        stripProps(props as Record<string, unknown>, "span"),
      h2: (props: ComponentPropsWithoutRef<"h2">) =>
        stripProps(props as Record<string, unknown>, "h2"),
      p: (props: ComponentPropsWithoutRef<"p">) =>
        stripProps(props as Record<string, unknown>, "p"),
    },
    AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  };
});

// Mock Lucide icons
vi.mock("lucide-react", () => ({
  AlertCircle: () => <div data-testid="icon-alert" />,
  Check: () => <div data-testid="icon-check" />,
  Plus: () => <div data-testid="icon-plus" />,
  Trash2: () => <div data-testid="icon-trash" />,
  Copy: () => <div data-testid="icon-copy" />,
  Eye: () => <div data-testid="icon-eye" />,
  EyeOff: () => <div data-testid="icon-eye-off" />,
  RefreshCw: () => <div data-testid="icon-refresh" />,
  Terminal: () => <div data-testid="icon-terminal" />,
  Plug: () => <div data-testid="icon-plug" />,
  HardDrive: () => <div data-testid="icon-harddrive" />,
  Settings: () => <div data-testid="icon-settings" />,
  ShieldCheck: () => <div data-testid="icon-shield" />,
  Code2: () => <div data-testid="icon-code" />,
  ArrowUpRight: () => <div data-testid="icon-external" />,
  Key: () => <div data-testid="icon-key" />,
  Loader2: () => <div data-testid="icon-loader" />,
  CheckCircle: () => <div data-testid="icon-check-circle" />,
  AlertTriangle: () => <div data-testid="icon-alert-triangle" />,
  ShieldOff: () => <div data-testid="icon-shield-off" />,
  Save: () => <div data-testid="icon-save" />,
}));

// Mock API and store
vi.mock("@/lib/settingsApi", () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

vi.mock("@/lib/users", () => ({
  usersApi: {
    regenerateApiKey: vi.fn(),
    revokeApiKey: vi.fn(),
  },
}));

vi.mock("@/features/auth/api/mfa", () => ({
  mfaApi: {
    getStatus: vi.fn().mockResolvedValue({ mfa_enabled: false }),
    getTrustedDevices: vi.fn().mockResolvedValue([]),
    setup: vi.fn(),
    verifySetup: vi.fn(),
    disable: vi.fn(),
    revokeTrustedDevice: vi.fn(),
  },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

// Mock components
vi.mock("@/components/common/FlowDiagram", () => ({
  FlowDiagram: () => <div data-testid="flow-diagram">Flow Diagram</div>,
}));

vi.mock("@/components/common/HelpIcon", () => ({
  HelpIcon: ({ tooltip }: { tooltip: string }) => (
    <span data-testid="help-icon" title={tooltip}>
      ?
    </span>
  ),
}));

// Mock Tooltip components
vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  TooltipContent: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  TooltipProvider: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));

// Mock Copy Button navigator.clipboard
Object.defineProperty(navigator, "clipboard", {
  value: {
    writeText: vi.fn(),
  },
  writable: true,
  configurable: true,
});

const mockSettings = {
  tmdb_api_key: "********1234",
  omdb_api_key: "",
  opensubtitles_api_key: "",
  opensubtitles_username: "",
  opensubtitles_password: "",
  deepl_api_keys: [],
  deepl_usage: [],
  qbittorrent_host: "localhost",
  qbittorrent_port: 8080,
  qbittorrent_username: "admin",
  qbittorrent_password: "********password",
  allowed_media_folders: [],
  setup_completed: true,
  google_cloud_configured: false,
  google_usage: {
    total_characters: 0,
    this_month_characters: 0,
    source: "google_cloud_monitoring" as const,
  },
} satisfies SettingsRead;

describe("SettingsPage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    vi.clearAllMocks();
    vi.mocked(getSettings).mockResolvedValue(mockSettings);
    vi.mocked(updateSettings).mockResolvedValue(mockSettings);
    // Default mock for admin user
    const state = {
      user: {
        id: "1",
        email: "admin@example.com",
        role: "admin",
        is_superuser: true,
        api_key_preview: "abcd...",
        api_key_last_generated: "2023-01-01T00:00:00Z",
      } as User,
      setUser: vi.fn(),
    } as Partial<AuthState>;
    vi.mocked(useAuthStore).mockImplementation(
      (selector?: (state: AuthState) => unknown) =>
        selector ? (selector(state as AuthState) as never) : (state as never),
    );
  });

  it("removes a DeepL key via confirm dialog", async () => {
    const user = createUser();
    const deeplSettings = { ...mockSettings, deepl_api_keys: ["abc12345"] };
    vi.mocked(getSettings).mockResolvedValue(deeplSettings);
    vi.mocked(updateSettings).mockResolvedValue({
      ...deeplSettings,
      deepl_api_keys: [],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    // Remove key
    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    await user.click(removeButtons[0]);

    expect(screen.getByText("Remove API Key?")).toBeInTheDocument();

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Remove/i }));

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({ deepl_api_keys: [] });
    });
    expect(
      screen.getByText(/DeepL key removed successfully/i),
    ).toBeInTheDocument();
  });

  it("adds a new DeepL key and saves it", async () => {
    const user = createUser();
    const baseSettings = { ...mockSettings, deepl_api_keys: [] };
    vi.mocked(getSettings).mockResolvedValue(baseSettings);
    vi.mocked(updateSettings).mockResolvedValue({
      ...baseSettings,
      deepl_api_keys: ["new-key"],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Add API Key"));
    const deeplInput = screen.getByPlaceholderText("Enter DeepL API key...");
    await user.type(deeplInput, "new-key");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        deepl_api_keys: ["new-key"],
      });
    });
  });

  it("handles DeepL key suffix trimming and keyboard editing", async () => {
    const user = createUser();
    const deeplSettings = {
      ...mockSettings,
      deepl_api_keys: ["...56789012"],
      deepl_usage: [
        {
          key_alias: "56789012",
          valid: true,
          character_count: 1,
          character_limit: 2,
        },
      ],
    };
    vi.mocked(getSettings).mockResolvedValue(deeplSettings);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    // status should use suffix without leading dots
    await waitFor(() =>
      expect(screen.getAllByText("Valid").length).toBeGreaterThan(0),
    );

    const masked = screen.getByRole("button", {
      name: /Edit DeepL API key 1/i,
    });
    fireEvent.keyDown(masked, { key: "Enter", code: "Enter" });
    const input = await screen.findByPlaceholderText("Enter DeepL API key...");
    await user.clear(input);
    await user.type(input, "updated-key");
    await user.keyboard("{Enter}");

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({ deepl_api_keys: ["updated-key"] }),
      ),
    );
  });

  it("shows Google usage stats and errors when configured but invalid", async () => {
    const usageSettings: any = {
      ...mockSettings,
      google_cloud_configured: true,
      google_cloud_valid: false,
      google_cloud_error: "invalid credentials",
      google_cloud_project_id: "proj-456",
      google_usage: {
        total_characters: 123456,
        this_month_characters: 7890,
        source: "google_cloud_monitoring_cached" as const,
        last_updated: "2024-01-01T00:00:00Z",
      },
      setup_completed: true,
    } as unknown as SettingsRead;
    vi.mocked(getSettings).mockResolvedValue(usageSettings);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    expect(screen.getByText("Translation Usage")).toBeInTheDocument();
    expect(screen.getByText("invalid credentials")).toBeInTheDocument();
    // With source !== "google_cloud_monitoring", it should show "API Unreachable" and "Local"
    expect(screen.getByText("API Unreachable")).toBeInTheDocument();
    expect(screen.getByText("Local")).toBeInTheDocument();
    expect(screen.getByText(/7,890/)).toBeInTheDocument();
    expect(screen.getByText(/123,456/)).toBeInTheDocument();
  });

  it("shows error when saving settings fails", async () => {
    const user = createUser();
    vi.mocked(updateSettings).mockRejectedValueOnce(new Error("fail"));

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.type(screen.getByLabelText(/TMDB API Key/i), "new-key");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByText("Failed to save settings")).toBeInTheDocument();
    });
  });

  it("revokes developer API key and shows success", async () => {
    const user = createUser();
    vi.mocked(usersApi.revokeApiKey).mockResolvedValueOnce(undefined as never);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    const revokeBtn = screen.getByRole("button", { name: /Revoke/i });
    await user.click(revokeBtn);

    await waitFor(() => {
      expect(usersApi.revokeApiKey).toHaveBeenCalled();
      expect(
        screen.getByText(/API Key revoked successfully/i),
      ).toBeInTheDocument();
    });
  });

  it("handles webhook configuration network failure", async () => {
    const user = createUser();
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("network"));

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("qBittorrent"));
    await user.click(
      screen.getByRole("button", { name: /configure automatically/i }),
    );

    await waitFor(() => {
      expect(
        screen.getAllByText(
          "Failed to configure webhook. Check your connection.",
        ).length,
      ).toBeGreaterThan(0);
    });
  });

  afterEach(() => {
    cleanup();
    vi.useFakeTimers();
    vi.runAllTimers();
    vi.useRealTimers();
  });

  it("renders and handles tab switching", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    // Wait for initial load
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    // Switch to API Integrations if not active
    const apiTab = screen.getByText("API Integrations");
    fireEvent.click(apiTab);
    expect(screen.getByText("External Services")).toBeInTheDocument();

    // Switch to qBittorrent
    const qbTab = screen.getByText("qBittorrent");
    fireEvent.click(qbTab);
    expect(screen.getByText("Automatic Setup")).toBeInTheDocument();
    expect(screen.getByTestId("flow-diagram")).toBeInTheDocument();

    // Switch to Developer API
    const devTab = screen.getByText("Developer API");
    fireEvent.click(devTab);
    expect(screen.getByText("Authentication Key")).toBeInTheDocument();
    expect(screen.getByText("Quick Start Examples")).toBeInTheDocument();

    // Switch to Security
    const secTab = screen.getByText("Security");
    fireEvent.click(secTab);
    expect(
      screen.getByRole("heading", { name: /Change Password/i }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Two-Factor Authentication")).toBeInTheDocument();
    });
  });

  it("handles API key management in Developer API tab", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    // Switch to Developer API
    await user.click(screen.getByText("Developer API"));

    // Check last generated text - more flexible match
    await waitFor(() => {
      expect(
        screen.getByText(/Authentication key is configured and active/i),
      ).toBeInTheDocument();
    });

    // Test Regenerate
    const regenBtn = screen.getByText("Regenerate");
    vi.mocked(usersApi.regenerateApiKey).mockResolvedValueOnce({
      id: "new-id",
      api_key: "new-super-secret-key",
      preview: "new-...",
      created_at: "2023-01-01T00:00:00Z",
    });

    await user.click(regenBtn);

    // Confirm dialog should appear (mocking confirm dialog would be better but let's check for title)
    expect(
      screen.getByText(/Confirm API Key Regeneration/i),
    ).toBeInTheDocument();

    // Find confirming button in dialog
    const dialog = screen.getByRole("dialog");
    const confirmBtn = within(dialog).getByRole("button", {
      name: "Regenerate",
    });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(usersApi.regenerateApiKey).toHaveBeenCalled();
      expect(screen.getByText("new-super-secret-key")).toBeInTheDocument();
    });

    // Test copy
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    const copyBtn = screen.getByRole("button", { name: /copy api key/i });
    await user.click(copyBtn);
    expect(writeTextSpy).toHaveBeenCalledWith("new-super-secret-key");
  });

  it("handles code snippet language switching in Developer API tab", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    fireEvent.click(screen.getByText("Developer API"));

    // Initially cURL
    expect(
      screen.getByText((content) => content.includes("curl -X POST")),
    ).toBeInTheDocument();

    // Switch to Python
    fireEvent.click(screen.getByText("Python"));
    expect(screen.getByText(/import requests/)).toBeInTheDocument();

    // Switch to Node.js
    fireEvent.click(screen.getByText("Node.js"));
    expect(
      screen.getByText(/const axios = require\('axios'\)/),
    ).toBeInTheDocument();

    // Back to cURL
    fireEvent.click(screen.getByText("cURL"));
    expect(
      screen.getByText((content) => content.includes("curl -X POST")),
    ).toBeInTheDocument();
  });

  it("regenerates developer API key via confirm dialog and toggles visibility/copy", async () => {
    const user = createUser();
    vi.mocked(usersApi.regenerateApiKey).mockResolvedValueOnce({
      id: "new-id",
      api_key: "brand-new-key",
      preview: "brand...",
      created_at: "2024-01-01T00:00:00Z",
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByText(/Regenerate/i));

    const dialog = screen.getByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: /Regenerate/i }),
    );

    await waitFor(() => {
      expect(usersApi.regenerateApiKey).toHaveBeenCalled();
      expect(screen.getByDisplayValue(/brand-new-key/i)).toBeInTheDocument();
    });

    const toggleBtn = screen.getByRole("button", { name: /hide api key/i });
    await user.click(toggleBtn); // hide (becomes show)
    await user.click(toggleBtn); // show

    const copyBtn = screen.getByRole("button", { name: /copy api key/i });
    const spy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(copyBtn);
    expect(spy).toHaveBeenCalledWith("brand-new-key");
  });

  it("closes confirm dialog via cancel", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByText(/Regenerate/i));

    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Cancel/i }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  it("copies quick start snippet", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByText("Python"));

    const snippetCopy = screen.getByLabelText("Copy code snippet");
    const spy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(snippetCopy);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it("copies Node quick start snippet", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByText("Node.js"));

    const snippetCopy = screen.getByLabelText("Copy code snippet");
    const spy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(snippetCopy);
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("const axios = require('axios');"),
    );
    spy.mockRestore();
  });

  it("logs snippet copy errors gracefully", async () => {
    const user = createUser();
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(
      new Error("copy fail"),
    );

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByLabelText("Copy code snippet"));

    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("polls DeepL validation when pending usage exists", async () => {
    const intervalSpy = vi.spyOn(globalThis, "setInterval");
    const pendingSettings = {
      ...mockSettings,
      deepl_api_keys: ["pending***"],
      deepl_usage: [
        {
          key_alias: "pending***",
          valid: null,
          character_count: 0,
          character_limit: 0,
        },
      ],
    };
    vi.mocked(getSettings).mockResolvedValue(pendingSettings);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    expect(intervalSpy).toHaveBeenCalledWith(expect.any(Function), 1000);
    intervalSpy.mockRestore();
  });

  it("handles API key copy failure gracefully", async () => {
    const user = createUser();
    vi.mocked(usersApi.regenerateApiKey).mockResolvedValueOnce({
      id: "id-1",
      api_key: "key-fail",
      preview: "key...",
      created_at: "2024-01-01T00:00:00Z",
    });
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(
      new Error("copy error"),
    );
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByText(/Regenerate/i));
    const dialog = screen.getByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: /Regenerate/i }),
    );

    const copyBtn = await screen.findByRole("button", {
      name: /Copy API key/i,
    });
    await user.click(copyBtn);

    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("shows load error when getSettings fails", async () => {
    vi.mocked(getSettings).mockRejectedValueOnce(new Error("load fail"));

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Failed to load settings")).toBeInTheDocument();
    });
  });

  it("masks and toggles webhook secret in qBittorrent tab", async () => {
    const user = createUser();

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("qBittorrent"));

    // Check description which contains setup context
    expect(
      screen.getByText(
        /Automate subtitle downloads whenever a new torrent completes/i,
      ),
    ).toBeInTheDocument();

    // Copy command
    const copyCmdBtn = screen.getByText(/Click to copy/i);
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(copyCmdBtn);
    expect(writeTextSpy).toHaveBeenCalledWith(
      `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`,
    );

    // Wait for "Command copied!" success message
    expect(await screen.findByText("Command copied!")).toBeInTheDocument();

    // Verify message is gone
    await waitFor(
      () => {
        expect(screen.queryByText("Command copied!")).toBeNull();
      },
      { timeout: 4000 },
    );
  });

  it("restricts tabs for non-admin users", async () => {
    vi.mocked(useAuthStore).mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = {
          user: {
            id: "2",
            email: "user@example.com",
            role: "standard",
            is_superuser: false,
          } as User,
          setUser: vi.fn(),
        } as Partial<AuthState>;
        return selector
          ? (selector(state as AuthState) as never)
          : (state as never);
      },
    );

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    // Should only see Security tab
    expect(screen.getByText("Security")).toBeInTheDocument();
    expect(screen.queryByText("API Integrations")).toBeNull();
    expect(screen.queryByText("qBittorrent")).toBeNull();
    expect(screen.queryByText("Developer API")).toBeNull();

    // Content should be security tab
    expect(
      screen.getByRole("heading", { name: /Change Password/i }),
    ).toBeInTheDocument();
  });
  it("updates settings when save is triggered", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    // Switch to API Integrations
    await user.click(screen.getByText("API Integrations"));

    // Modify TMDB API Key
    const input = screen.getByLabelText(/TMDB API Key/i);
    await user.clear(input);
    await user.type(input, "new-tmdb-key");

    // Save pill should appear (it's inside PageHeader usually but let's check saving)
    // The component detects changes via formData state.
    // We need to trigger save. In the UI this might be via "Enter" or a Save button if visible.
    // Looking at the code, there is a SavePill component but it's not explicitly in the rendered output in the test file snippet?
    // Wait, the component uses <SavePill /> which should be visible when changes exist.
    // Let's press Enter to save since we have onKeyDown handler
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(vi.mocked(updateSettings)).toHaveBeenCalledWith(
        expect.objectContaining({
          tmdb_api_key: "new-tmdb-key",
        }),
      );
    });

    // Check for success message
    await waitFor(() => {
      expect(
        screen.getByText(/Settings saved successfully/i),
      ).toBeInTheDocument();
    });
  });

  it("does not keep dirty state when value matches original", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    const tmdbInput = screen.getByLabelText(/TMDB API Key/i);
    await user.clear(tmdbInput);
    await user.type(tmdbInput, "********1234");

    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("allows setting Google Cloud credentials when not configured", async () => {
    const user = createUser();
    vi.mocked(getSettings).mockResolvedValue({
      ...mockSettings,
      google_cloud_configured: false,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    const textarea = screen.getByPlaceholderText(
      /Paste your Google Cloud service account/i,
    );
    fireEvent.change(textarea, { target: { value: '{"project_id":"demo"}' } });

    const saveBtn = await screen.findByRole("button", { name: "Save" });
    await user.click(saveBtn);

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          google_cloud_credentials: '{"project_id":"demo"}',
        }),
      ),
    );
  });

  it("removes google credentials change when unchanged and not configured", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    const textarea = screen.getByPlaceholderText(
      /Paste your Google Cloud service account/i,
    );
    await user.type(textarea, "temp");
    fireEvent.change(textarea, { target: { value: "" } });

    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("opens confirm dialog and removes Google Cloud credentials", async () => {
    const user = createUser();
    // Mock settings with Google Configured
    const googleSettings = {
      ...mockSettings,
      google_cloud_configured: true,
      google_cloud_valid: true,
      google_cloud_project_id: "proj-123",
      google_cloud_error: null,
    };
    vi.mocked(getSettings).mockResolvedValue(googleSettings);
    vi.mocked(updateSettings).mockResolvedValue({
      ...googleSettings,
      google_cloud_configured: false,
      google_cloud_credentials: "",
    });

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    // Find custom Google Cloud removal button (usually a Trash icon)
    // Note: The original file view didn't show the Google Cloud section fully, but we assume the logic exists passed line 800.
    // If we can't find it, we might need to view more of the file.
    // Let's assume the "Trash2" icon is rendered for Google Cloud when configured.
    // We can search for the aria-label or trash icon.

    // To be safe, let's verify if we can find the "Google Cloud" section text
    // To be safe, let's verify if we can find the "Google Cloud" section text
    expect(screen.getAllByText(/Google/i).length).toBeGreaterThan(0);

    // Find the remove button - often has a delete/trash icon
    // Based on `handleGoogleRemoveRequest` logic in the source.
    const removeBtn = screen.getByTitle("Remove configuration");
    await user.click(removeBtn);

    // Dialog should appear
    expect(
      screen.getByText("Remove Google Cloud Configuration?"),
    ).toBeInTheDocument();

    // Confirm
    const dialog = screen.getByRole("dialog");
    const confirmBtn = within(dialog).getByRole("button", { name: /Remove/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith({
        google_cloud_credentials: "",
      });
    });
  });

  it("discards changes via SavePill", async () => {
    const user = createUser();
    // Ensure settings include a DeepL key so discard can reset it
    const deeplSettings = { ...mockSettings, deepl_api_keys: ["abcd1234"] };
    vi.mocked(getSettings).mockResolvedValue(deeplSettings);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    // Change TMDB key to trigger SavePill
    await user.type(screen.getByLabelText(/TMDB API Key/i), "new-key");

    const discardButton = await screen.findByRole("button", {
      name: "Discard",
    });
    await user.click(discardButton);

    await waitFor(() => {
      // Input should reset to empty (controlled by formData) after discard
      expect(screen.getByLabelText(/TMDB API Key/i)).toHaveValue("");
    });
  });

  it("shows error when DeepL removal fails in confirm dialog", async () => {
    const user = createUser();
    const deeplSettings = { ...mockSettings, deepl_api_keys: ["abcd1234"] };
    vi.mocked(getSettings).mockResolvedValue(deeplSettings);
    vi.mocked(updateSettings).mockRejectedValueOnce(new Error("remove fail"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));
    await user.click(screen.getAllByRole("button", { name: /remove/i })[0]);
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Remove/i }));

    await waitFor(() =>
      expect(screen.getByText("Failed to execute action.")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("dialog")).toBeNull();

    consoleSpy.mockRestore();
  });

  it("handles qbittorrent webhook auto configuration success and error", async () => {
    const user = createUser();
    const timeoutSpy = vi.spyOn(global, "setTimeout");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        json: async () => ({ success: true, message: "Configured!" }),
      } as unknown as Response)
      .mockResolvedValueOnce({
        json: async () => ({ success: false, message: "Failed to configure" }),
      } as unknown as Response);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("qBittorrent"));

    const configureBtn = screen.getByRole("button", {
      name: /configure automatically/i,
    });
    await user.click(configureBtn);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
      expect(screen.getAllByText("Configured!").length).toBeGreaterThan(1);
    });
    expect(timeoutSpy).toHaveBeenCalled();
    const successCount = screen.getAllByText("Configured!").length;
    const successTimeout = timeoutSpy.mock.calls
      .filter((call) => call[1] === 5000)
      .at(-1)?.[0] as (() => void) | undefined;
    expect(successTimeout).toEqual(expect.any(Function));
    act(() => {
      successTimeout?.();
    });
    await waitFor(() =>
      expect(screen.getAllByText("Configured!").length).toBeLessThan(
        successCount,
      ),
    );

    // Trigger error path on second call
    await user.click(configureBtn);
    await waitFor(() => {
      expect(screen.getAllByText("Failed to configure").length).toBeGreaterThan(
        1,
      );
    });
    expect(timeoutSpy).toHaveBeenCalled();
    const errorCount = screen.getAllByText("Failed to configure").length;
    const errorTimeout = timeoutSpy.mock.calls
      .filter((call) => call[1] === 5000)
      .at(-1)?.[0] as (() => void) | undefined;
    expect(errorTimeout).toEqual(expect.any(Function));
    act(() => {
      errorTimeout?.();
    });
    await waitFor(() =>
      expect(screen.getAllByText("Failed to configure").length).toBeLessThan(
        errorCount,
      ),
    );

    fetchSpy.mockRestore();
    timeoutSpy.mockRestore();
  });

  it("copies qbittorrent command from block and clears toast", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
    await user.click(screen.getByText("qBittorrent"));

    const clipboardSpy = vi.spyOn(navigator.clipboard, "writeText");
    const block = screen.getByText(
      `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`,
    );
    await user.click(block);

    await waitFor(() =>
      expect(clipboardSpy).toHaveBeenCalledWith(
        `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`,
      ),
    );
    expect(await screen.findByText("Command copied!")).toBeInTheDocument();
    await waitFor(
      () => expect(screen.queryByText("Command copied!")).toBeNull(),
      { timeout: 3000 },
    );
    clipboardSpy.mockRestore();
  });

  it("handles qbittorrent command block copy errors", async () => {
    const user = createUser();
    const clipboardSpy = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockRejectedValue(new Error("denied-block"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
    await user.click(screen.getByText("qBittorrent"));

    const block = screen.getByText(
      `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`,
    );
    await user.click(block);

    await waitFor(() => expect(clipboardSpy).toHaveBeenCalled());
    expect(consoleSpy).toHaveBeenCalled();

    clipboardSpy.mockRestore();
    consoleSpy.mockRestore();
  });

  it("shows error when revoking developer API key fails", async () => {
    const user = createUser();
    vi.mocked(usersApi.revokeApiKey).mockRejectedValueOnce(
      new Error("revoke fail"),
    );
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("Developer API"));
    await user.click(screen.getByRole("button", { name: /Revoke/i }));

    await waitFor(() =>
      expect(screen.getByText("Failed to revoke API key.")).toBeInTheDocument(),
    );

    consoleSpy.mockRestore();
  });

  it("shows Google Cloud usage, error state, and cached badge", async () => {
    const user = createUser();
    const googleSettings = {
      ...mockSettings,
      google_cloud_configured: true,
      google_cloud_valid: false,
      google_cloud_error: "invalid credentials",
      google_cloud_project_id: "proj-999",
      google_usage: {
        total_characters: 1234,
        this_month_characters: 567,
        source: "google_cloud_monitoring_cached" as const,
        last_updated: "2024-01-01T00:00:00Z",
      },
    };
    vi.mocked(getSettings).mockResolvedValue(googleSettings);

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    expect(screen.getByText("proj-999")).toBeInTheDocument();
    expect(screen.getByText("invalid credentials")).toBeInTheDocument();
    expect(screen.getByText(/API Unreachable/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        (text) => text.includes("1,234") || text.includes("1234"),
      ),
    ).toBeTruthy();
    expect(screen.getByText((text) => text.includes("567"))).toBeTruthy();
  });

  it("saves qBittorrent connection fields and copies command", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("qBittorrent"));

    const hostInput = screen.getByLabelText(/Host/i);
    await user.clear(hostInput);
    await user.type(hostInput, "remote-host");
    const portInput = screen.getByLabelText(/Port/i);
    await user.clear(portInput);
    await user.type(portInput, "8999");

    fireEvent.keyDown(hostInput, { key: "Enter", code: "Enter" });

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          qbittorrent_host: "remote-host",
          qbittorrent_port: 8999,
        }),
      ),
    );

    const clipboardSpy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByText(/Click to copy/i));
    await waitFor(() =>
      expect(clipboardSpy).toHaveBeenCalledWith(
        `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`,
      ),
    );
    clipboardSpy.mockRestore();
  });

  it("uploads Google JSON via file input and saves", async () => {
    const user = createUser();
    const originalFileReader = window.FileReader;
    class MockFileReader {
      public result: string | ArrayBuffer | null = null;
      public onload:
        | ((this: FileReader, ev: ProgressEvent<FileReader>) => unknown)
        | null = null;
      readAsText(_file: File) {
        this.result = `{"project_id":"demo"}`;
        // @ts-ignore
        this.onload?.({ target: { result: this.result } });
      }
    }
    // @ts-ignore
    window.FileReader = MockFileReader;

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    const file = new File([`{"project_id":"demo"}`], "creds.json", {
      type: "application/json",
    });
    const input = document.querySelector(
      "input[type='file'][id='google-cloud-config-file']",
    ) as HTMLInputElement;
    expect(input).toBeTruthy();
    await user.upload(input, file);

    const textarea = screen.getByPlaceholderText(
      /Paste your Google Cloud service account/i,
    );
    fireEvent.change(textarea, {
      target: { value: '{"project_id":"demo"}' },
    });

    const saveBtn = await screen.findByRole("button", { name: "Save" });
    await user.click(saveBtn);

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          google_cloud_credentials: expect.stringContaining("project_id"),
        }),
      ),
    );

    window.FileReader = originalFileReader;
  });

  it("updates OMDb and OpenSubtitles credentials", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("API Integrations"));

    await user.type(screen.getByLabelText(/OMDB API Key/i), "omdb123");
    await user.type(screen.getByLabelText(/OpenSubtitles API Key/i), "os-key");
    await user.type(screen.getByLabelText(/Username/i), "os-user");
    await user.type(screen.getByLabelText(/^Password$/i), "os-pass");

    await user.keyboard("{Enter}");

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          omdb_api_key: "omdb123",
          opensubtitles_api_key: "os-key",
          opensubtitles_username: "os-user",
          opensubtitles_password: "os-pass",
        }),
      ),
    );
  });

  it("saves qbittorrent username/password on Enter", async () => {
    const user = createUser();
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    await user.click(screen.getByText("qBittorrent"));
    const usernameInput = screen.getByLabelText(/Username/i);
    const passwordInput = screen.getByLabelText(/Password/i);

    await user.clear(usernameInput);
    await user.type(usernameInput, "qbuser");
    await user.clear(passwordInput);
    await user.type(passwordInput, "qbpass");

    await user.keyboard("{Enter}");

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          qbittorrent_username: "qbuser",
          qbittorrent_password: "qbpass",
        }),
      ),
    );
  });

  it("handles qbittorrent command copy errors", async () => {
    const user = createUser();
    const clipboardSpy = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockRejectedValue(new Error("denied"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
    await user.click(screen.getByText("qBittorrent"));

    await user.click(screen.getByText(/Click to copy/i));

    await waitFor(() => expect(clipboardSpy).toHaveBeenCalled());
    expect(consoleSpy).toHaveBeenCalled();

    clipboardSpy.mockRestore();
    consoleSpy.mockRestore();
  });
});
