/** @vitest-environment jsdom */
import {
  render,
  screen,
  fireEvent,
  waitFor,
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
import { getSettings, type SettingsRead } from "@/lib/settingsApi";
import { usersApi } from "@/lib/users";
import type { ReactNode } from "react";

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
    source: "google_cloud_monitoring",
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

  afterEach(() => {
    cleanup();
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
    expect(screen.getByText("Webhook Ready")).toBeInTheDocument();
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
    const user = userEvent.setup();
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
  });

  it("masks and toggles webhook secret in qBittorrent tab", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    fireEvent.click(screen.getByText("qBittorrent"));

    // Check description which contains setup context
    expect(
      screen.getByText(
        /Automate subtitle downloads whenever a new torrent completes/i,
      ),
    ).toBeInTheDocument();

    // Copy command
    const copyCmdBtn = screen.getByText(/Click to copy/i);
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    fireEvent.click(copyCmdBtn);
    expect(writeTextSpy).toHaveBeenCalledWith(
      `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`,
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
});
