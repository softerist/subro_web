/**
 * @vitest-environment jsdom
 */
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import { JobForm } from "../features/jobs/components/JobForm";
import { jobsApi } from "../features/jobs/api/jobs";
import { useAuthStore } from "../store/authStore";

// Mock APIs
vi.mock("../features/jobs/api/jobs", () => ({
  jobsApi: {
    getAllowedFolders: vi.fn(),
    getRecentTorrents: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
  },
}));

// Mock StorageManagerDialog to simplify
vi.mock("../features/jobs/components/StorageManagerDialog", () => ({
  StorageManagerDialog: () => (
    <div data-testid="mock-storage-manager">Storage Manager</div>
  ),
}));

// Mock UI Select components to be standard select/options for JSDOM the tests
vi.mock("@/components/ui/select", () => {
  const SelectItem = ({ children, value }: any) => {
    const getText = (node: any): string => {
      if (typeof node === "string") return node;
      if (typeof node === "number") return String(node);
      if (Array.isArray(node)) return node.map(getText).join("");
      if (node && node.props && node.props.children)
        return getText(node.props.children);
      return "";
    };

    const text = getText(children) || value;

    return <option value={value}>{text}</option>;
  };

  // Recursively find all SelectItem components
  const findSelectItems = (children: any): any[] => {
    if (!children) return [];
    if (Array.isArray(children)) {
      return children.flatMap(findSelectItems);
    }
    if (
      children &&
      typeof children === "object" &&
      "type" in children &&
      children.type === SelectItem
    ) {
      return [children];
    }
    if (
      children &&
      typeof children === "object" &&
      "props" in children &&
      children.props?.children
    ) {
      return findSelectItems(children.props.children);
    }
    return [];
  };

  return {
    Select: ({
      children,
      onValueChange,
      value,
      onOpenChange,
      ...props
    }: any) => {
      return (
        <select
          {...props}
          value={value}
          onClick={() => onOpenChange && onOpenChange(true)}
          onChange={(e) => {
            onValueChange(e.target.value);
          }}
        >
          {children}
        </select>
      );
    },
    SelectTrigger: () => null,
    SelectValue: () => null,
    SelectContent: ({ children }: any) => {
      // Only render actual SelectItem components, ignoring headers and dividers
      const items = findSelectItems(children);
      return <>{items}</>;
    },
    SelectItem,
  };
});

// Mock Sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

// JSDOM doesn't implement scrollIntoView or PointerEvent stuff for Radix
window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.HTMLElement.prototype.hasPointerCapture = vi.fn();
window.HTMLElement.prototype.releasePointerCapture = vi.fn();

// Mock PointerEvent which is missing in JSDOM
if (!window.PointerEvent) {
  class PointerEvent extends MouseEvent {
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
    }
  }
  window.PointerEvent = PointerEvent as any;
}

describe("JobForm", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    queryClient.clear();
    // Set a mock token to enable the form
    useAuthStore.getState().setAccessToken("mock-token");
  });

  it("renders the form with initial values", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue([
      "/media/movies",
      "/media/tv",
    ]);

    render(<JobForm />, { wrapper });

    expect(screen.getByText(/target folder/i)).toBeDefined();
    expect(screen.getAllByText(/language/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /start job/i })).toBeDefined();
  });

  it("submits the form successfully", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue(["/media/movies"]);
    (jobsApi.create as any).mockResolvedValue({
      id: "job-1",
      status: "pending",
    });

    render(<JobForm />, { wrapper });

    // Wait for folders to load
    await waitFor(() =>
      expect(screen.queryByText(/loading\.\.\./i)).toBeNull(),
    );

    // Wait for option to render
    await waitFor(() =>
      expect(screen.getAllByText("/media/movies")[0]).toBeDefined(),
    );

    // Select a folder
    const select = screen.getByTestId("folder_path");
    fireEvent.change(select, { target: { value: "/media/movies" } });
    await waitFor(() => expect((select as any).value).toBe("/media/movies"));

    // Click submit
    const submitButton = screen.getByRole("button", { name: /start job/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(jobsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          folder_path: "/media/movies",
          language: "ro",
          log_level: "INFO",
        }),
        expect.anything(),
      );
    });
  });

  it("renders recent torrents in the dropdown and allows selection", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue(["/media/movies"]);
    (jobsApi.getRecentTorrents as any).mockResolvedValue([
      {
        name: "Movie 1",
        save_path: "/downloads",
        content_path: "/downloads/movie1",
        completed_on: "2023-01-01",
      },
    ]);
    (jobsApi.create as any).mockResolvedValue({
      id: "job-2",
      status: "pending",
    });

    render(<JobForm />, { wrapper });

    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    const select = screen.getByTestId("folder_path");
    // Open the dropdown to trigger the query
    fireEvent.click(select);

    // Wait for the option to appear
    await waitFor(() => {
      expect(screen.getByText("Movie 1")).toBeDefined();
    });

    // Select it (value prefers content_path)
    fireEvent.change(select, { target: { value: "/downloads/movie1" } });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(jobsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          folder_path: "/downloads/movie1",
        }),
        expect.anything(),
      );
    });
  });

  it("uses save_path when content_path is not available", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue([]);
    (jobsApi.getRecentTorrents as any).mockResolvedValue([
      {
        name: "Torrent Without Content Path",
        save_path: "/downloads/torrent-folder",
        content_path: null,
        completed_on: "2023-01-01",
      },
    ]);
    (jobsApi.create as any).mockResolvedValue({
      id: "job-3",
      status: "pending",
    });

    render(<JobForm />, { wrapper });

    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());

    const select = screen.getByTestId("folder_path");
    // Open the dropdown to trigger the query
    fireEvent.click(select);

    // Wait for the torrent option to appear
    await waitFor(() => {
      expect(screen.getByText("Torrent Without Content Path")).toBeDefined();
    });

    // Select it (value should be save_path since content_path is null)
    fireEvent.change(select, {
      target: { value: "/downloads/torrent-folder" },
    });

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(jobsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          folder_path: "/downloads/torrent-folder",
        }),
        expect.anything(),
      );
    });
  });

  it("handles null allowedFolders gracefully", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue(null);
    (jobsApi.getRecentTorrents as any).mockResolvedValue([
      {
        name: "Test Torrent",
        save_path: "/downloads",
        content_path: "/downloads/test",
        completed_on: "2023-01-01",
      },
    ]);

    render(<JobForm />, { wrapper });

    const select = screen.getByTestId("folder_path");
    // Open the dropdown to trigger the query
    fireEvent.click(select);

    // Should show torrent but not crash on null allowedFolders
    await waitFor(() => {
      expect(screen.getByText("Test Torrent")).toBeDefined();
    });

    // "Allowed Folders" header should NOT appear when allowedFolders is null
    expect(screen.queryByText("Allowed Folders")).toBeNull();
  });

  it("shows error toast on submission failure", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue(["/media/movies"]);
    const mockError = new Error("API Error");
    (mockError as any).response = {
      data: { detail: { code: "PATH_NOT_ALLOWED" } },
    };
    (jobsApi.create as any).mockRejectedValue(mockError);

    render(<JobForm />, { wrapper });

    // Wait for folders to load
    await waitFor(() =>
      expect(screen.queryByText(/loading\.\.\./i)).toBeNull(),
    );

    await waitFor(() =>
      expect(screen.getAllByText("/media/movies")[0]).toBeDefined(),
    );

    // Select folder
    const folderSelect = screen.getByTestId("folder_path");
    fireEvent.change(folderSelect, { target: { value: "/media/movies" } });
    await waitFor(() =>
      expect((folderSelect as any).value).toBe("/media/movies"),
    );
    fireEvent.blur(folderSelect);

    // Select language
    const langSelect = screen.getByTestId("language");
    fireEvent.change(langSelect, { target: { value: "en" } });
    fireEvent.blur(langSelect);

    // Select log level
    const logSelect = screen.getByTestId("log_level");
    fireEvent.change(logSelect, { target: { value: "ERROR" } });
    fireEvent.blur(logSelect);

    // Submit
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(
      () => {
        expect(vi.mocked(toast.error)).toHaveBeenCalled();
        const lastCall = vi.mocked(toast.error).mock.calls[0][0];
        expect(lastCall).toContain("Folder is not in allowed media folders");
      },
      { timeout: 3000 },
    );
  });

  it("surfaces string detail messages from the API", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue(["/media/movies"]);
    const mockError = new Error("Generic failure");
    (mockError as any).response = { data: { detail: "Custom detail message" } };
    (jobsApi.create as any).mockRejectedValue(mockError);

    render(<JobForm />, { wrapper });
    await waitFor(() =>
      expect(screen.queryByText(/loading\.\.\./i)).toBeNull(),
    );

    await waitFor(() =>
      expect(screen.getAllByText("/media/movies")[0]).toBeDefined(),
    );

    const select = screen.getByTestId("folder_path");
    fireEvent.change(select, {
      target: { value: "/media/movies" },
    });
    await waitFor(() => expect((select as any).value).toBe("/media/movies"));
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to start job: Custom detail message",
      );
    });
  });

  it("falls back to the error message when no detail is provided", async () => {
    (jobsApi.getAllowedFolders as any).mockResolvedValue(["/media/movies"]);
    const mockError = new Error("Network down");
    (mockError as any).response = { data: {} };
    (jobsApi.create as any).mockRejectedValue(mockError);

    render(<JobForm />, { wrapper });
    await waitFor(() =>
      expect(screen.queryByText(/loading\.\.\./i)).toBeNull(),
    );

    await waitFor(() =>
      expect(screen.getAllByText("/media/movies")[0]).toBeDefined(),
    );

    const select = screen.getByTestId("folder_path");
    fireEvent.change(select, {
      target: { value: "/media/movies" },
    });
    await waitFor(() => expect((select as any).value).toBe("/media/movies"));
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to start job: Network down",
      );
    });
  });
});
