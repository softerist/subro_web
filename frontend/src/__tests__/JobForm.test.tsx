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

// Mock APIs
vi.mock("../features/jobs/api/jobs", () => ({
  jobsApi: {
    getAllowedFolders: vi.fn().mockResolvedValue([]),
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

// Mock FolderBrowser — unit test form logic independently from browsing UX
vi.mock("../features/jobs/components/FolderBrowser", () => ({
  FolderBrowser: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <div data-testid="folder-browser-mock">
      <input
        data-testid="folder-browser-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        data-testid="folder-browser-select"
        onClick={() => onChange("/media/movies")}
      >
        Select Folder
      </button>
    </div>
  ),
}));

// Mock UI Select components to be standard select/options for JSDOM tests
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
    Select: ({ children, onValueChange, value, ...props }: any) => {
      return (
        <select
          {...props}
          value={value}
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
  });

  it("renders the form with initial values", () => {
    render(<JobForm />, { wrapper });

    expect(screen.getByText(/target folder/i)).toBeDefined();
    expect(screen.getAllByText(/language/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /start job/i })).toBeDefined();
  });

  it("renders the mocked folder browser", () => {
    render(<JobForm />, { wrapper });

    expect(screen.getByTestId("folder-browser-mock")).toBeDefined();
    expect(screen.getByTestId("folder-browser-select")).toBeDefined();
  });

  it("submits the form successfully after selecting a folder", async () => {
    (jobsApi.create as any).mockResolvedValue({
      id: "job-1",
      status: "pending",
    });

    render(<JobForm />, { wrapper });

    // Select a folder via the mock FolderBrowser
    fireEvent.click(screen.getByTestId("folder-browser-select"));

    // Submit the form
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

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

  it("shows success toast on successful submission", async () => {
    (jobsApi.create as any).mockResolvedValue({
      id: "job-1",
      status: "pending",
    });

    render(<JobForm />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-select"));
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Job started successfully");
    });
  });

  it("shows error toast on submission failure with PATH_NOT_ALLOWED", async () => {
    const mockError = new Error("API Error");
    (mockError as any).response = {
      data: { detail: { code: "PATH_NOT_ALLOWED" } },
    };
    (jobsApi.create as any).mockRejectedValue(mockError);

    render(<JobForm />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-select"));
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
    const mockError = new Error("Generic failure");
    (mockError as any).response = {
      data: { detail: "Custom detail message" },
    };
    (jobsApi.create as any).mockRejectedValue(mockError);

    render(<JobForm />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-select"));
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to start job: Custom detail message",
      );
    });
  });

  it("falls back to the error message when no detail is provided", async () => {
    const mockError = new Error("Network down");
    (mockError as any).response = { data: {} };
    (jobsApi.create as any).mockRejectedValue(mockError);

    render(<JobForm />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-select"));
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to start job: Network down",
      );
    });
  });
});
