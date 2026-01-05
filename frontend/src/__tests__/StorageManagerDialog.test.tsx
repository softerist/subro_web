/* eslint-disable @typescript-eslint/no-explicit-any */
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
import { StorageManagerDialog } from "../features/jobs/components/StorageManagerDialog";
import { storagePathsApi } from "../features/jobs/api/storagePaths";

// Mock the API
vi.mock("../features/jobs/api/storagePaths", () => ({
  storagePathsApi: {
    getAll: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}));

// Mock Sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe("StorageManagerDialog", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    queryClient.clear();
  });

  it("renders the dialog trigger", () => {
    render(<StorageManagerDialog />, { wrapper });
    expect(screen.getByTestId("storage-manager-trigger")).toBeDefined();
  });

  it("lists storage paths when opened", async () => {
    const mockPaths = [
      { id: "1", path: "/media/movies", label: "Movies" },
      { id: "2", path: "/media/tv", label: "TV Shows" },
    ];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);

    render(<StorageManagerDialog />, { wrapper });

    // Open dialog
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));

    await waitFor(() => {
      expect(screen.getByText("/media/movies")).toBeDefined();
      expect(screen.getByText("Movies")).toBeDefined();
      expect(screen.getByText("/media/tv")).toBeDefined();
      expect(screen.getByText("TV Shows")).toBeDefined();
    });
  });

  it("can add a new storage path", async () => {
    (storagePathsApi.getAll as any).mockResolvedValue([]);
    (storagePathsApi.create as any).mockResolvedValue({
      id: "3",
      path: "/downloads",
      label: "Custom: downloads",
    });

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));

    const input = screen.getByPlaceholderText("/path/to/media");
    fireEvent.change(input, { target: { value: "/downloads" } });

    const addButton = screen.getByRole("button", { name: /add/i });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(storagePathsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          path: "/downloads",
          label: "Custom: downloads",
        }),
        expect.anything(),
      );
    });
  });

  it("can enter inline edit mode and update a label", async () => {
    const mockPaths = [{ id: "1", path: "/media", label: "Old Label" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
    (storagePathsApi.update as any).mockResolvedValue({
      id: "1",
      path: "/media",
      label: "New Label",
    });

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));

    await waitFor(() => screen.getByText("Old Label"));

    // Click edit button for the specific path
    const editButton = screen.getByLabelText(/edit label for \/media/i);
    fireEvent.click(editButton);

    // Should now show the input
    const input = screen.getByPlaceholderText("Path label...");
    fireEvent.change(input, { target: { value: "New Label" } });

    // Click save button
    const saveButton = screen.getByLabelText(/save changes/i);
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(storagePathsApi.update).toHaveBeenCalledWith("1", {
        label: "New Label",
      });
    });
  });
});
