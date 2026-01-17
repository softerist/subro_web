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
  const SelectItem = ({ children, value }: any) => (
    <option value={value}>
      {typeof children === "string" ? children : value}
    </option>
  );

  const flattenChildren = (value: any): any[] =>
    Array.isArray(value) ? value.flatMap(flattenChildren) : [value];

  const extractText = (node: any): string => {
    if (typeof node === "string") {
      return node;
    }
    if (Array.isArray(node)) {
      return node.map(extractText).join("");
    }
    if (node && typeof node === "object" && "props" in node) {
      return extractText(node.props?.children);
    }
    return "";
  };

  return {
    Select: ({ children, onValueChange, value, name }: any) => (
      <select
        data-testid={name}
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
      >
        {children}
      </select>
    ),
    SelectTrigger: () => null,
    SelectValue: () => null,
    SelectContent: ({ children }: any) => {
      const items = flattenChildren(children);
      return (
        <>
          {items.map((child, index) => {
            if (
              child &&
              typeof child === "object" &&
              "type" in child &&
              child.type === SelectItem
            ) {
              return child;
            }
            const label = extractText(child);
            if (!label) {
              return null;
            }
            return (
              <option key={`mock-option-${index}`} disabled value="">
                {label}
              </option>
            );
          })}
        </>
      );
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
      expect(screen.queryByText(/loading folders/i)).toBeNull(),
    );

    // Select a folder
    const select = screen.getByTestId("folder_path");
    fireEvent.change(select, { target: { value: "/media/movies" } });

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
      expect(screen.queryByText(/loading folders/i)).toBeNull(),
    );

    // Select folder
    const folderSelect = screen.getByTestId("folder_path");
    fireEvent.change(folderSelect, { target: { value: "/media/movies" } });
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
      expect(screen.queryByText(/loading folders/i)).toBeNull(),
    );

    fireEvent.change(screen.getByTestId("folder_path"), {
      target: { value: "/media/movies" },
    });
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
      expect(screen.queryByText(/loading folders/i)).toBeNull(),
    );

    fireEvent.change(screen.getByTestId("folder_path"), {
      target: { value: "/media/movies" },
    });
    fireEvent.click(screen.getByRole("button", { name: /start job/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to start job: Network down",
      );
    });
  });
});
