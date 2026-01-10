/**
 * @vitest-environment jsdom
 */
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
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

    const input = await screen.findByPlaceholderText("/path/to/media");
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

  it("shows create errors when API fails", async () => {
    (storagePathsApi.getAll as any).mockResolvedValue([]);
    (storagePathsApi.create as any).mockRejectedValue({
      response: { data: { detail: "Path invalid" } },
      message: "Path invalid",
    });

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));

    const input = await screen.findByPlaceholderText("/path/to/media");
    fireEvent.change(input, { target: { value: "/bad" } });

    fireEvent.click(screen.getByRole("button", { name: /add/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Error adding path",
        expect.objectContaining({ description: "Path invalid" }),
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

  it("blocks update when label is empty", async () => {
    const mockPaths = [{ id: "1", path: "/media", label: "" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));

    await waitFor(() => screen.getByText("/media"));
    fireEvent.click(screen.getByLabelText(/edit label for \/media/i));

    const saveButton = screen.getByLabelText(/save changes/i);
    fireEvent.click(saveButton);

    expect(toast.error).toHaveBeenCalledWith("Label cannot be empty");
    expect(storagePathsApi.update).not.toHaveBeenCalled();
  });

  it("shows update errors when API fails via Enter key", async () => {
    const mockPaths = [{ id: "1", path: "/media", label: "Old Label" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
    const apiError = new Error("Update failed");
    (apiError as any).response = { data: { detail: "Update failed" } };
    (storagePathsApi.update as any).mockRejectedValue(apiError);

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));
    await waitFor(() => screen.getByText("Old Label"));

    fireEvent.click(screen.getByLabelText(/edit label for \/media/i));
    const input = screen.getByPlaceholderText("Path label...");
    fireEvent.change(input, { target: { value: "New Label" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Update failed");
    });
  });

  it("cancels editing on Escape key", async () => {
    const mockPaths = [{ id: "1", path: "/media", label: "Old Label" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));
    await waitFor(() => screen.getByText("Old Label"));

    fireEvent.click(screen.getByLabelText(/edit label for \/media/i));
    const input = screen.getByPlaceholderText("Path label...");

    fireEvent.keyDown(input, { key: "Escape", code: "Escape" });

    await waitFor(() => {
      expect(screen.queryByPlaceholderText("Path label...")).toBeNull();
    });
  });

  it("deletes a path when clicking the delete button", async () => {
    const mockPaths = [{ id: "2", path: "/data", label: "Data" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
    (storagePathsApi.delete as any).mockResolvedValue(undefined);

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));
    await waitFor(() => screen.getByText("/data"));

    const row = screen.getByText("/data").closest("tr") as HTMLElement;
    const deleteButton =
      within(row)
        .getAllByRole("button")
        .find((btn) => !btn.ariaLabel) ??
      within(row).getAllByRole("button").slice(-1)[0];
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(storagePathsApi.delete).toHaveBeenCalledWith(
        "2",
        expect.anything(),
      );
    });
  });

  it("shows delete error when API fails", async () => {
    const mockPaths = [{ id: "2", path: "/data", label: "Data" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
    (storagePathsApi.delete as any).mockRejectedValue({
      response: { data: { detail: "Cannot delete" } },
      message: "Cannot delete",
    });

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));
    await waitFor(() => screen.getByText("/data"));

    const row = screen.getByText("/data").closest("tr") as HTMLElement;
    const deleteButton =
      within(row)
        .getAllByRole("button")
        .find((btn) => !btn.ariaLabel) ??
      within(row).getAllByRole("button").slice(-1)[0];
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Cannot delete");
    });
  });

  it("shows nested detail message when update fails", async () => {
    const mockPaths = [{ id: "1", path: "/media", label: "Old Label" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
    (storagePathsApi.update as any).mockRejectedValue({
      response: { data: { detail: { message: "Nested error" } } },
      message: "outer",
    });

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));
    await waitFor(() => screen.getByText("Old Label"));

    fireEvent.click(screen.getByLabelText(/edit label for \/media/i));
    const input = screen.getByPlaceholderText("Path label...");
    fireEvent.change(input, { target: { value: "New Label" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Nested error"),
    );
  });

  it("shows loaders during update and delete pending states", async () => {
    const mockPaths = [{ id: "1", path: "/media", label: "Label" }];
    (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
    let updateResolve: () => void = () => {};
    (storagePathsApi.update as any).mockImplementation(
      () =>
        new Promise((resolve) => {
          updateResolve = () =>
            resolve({ id: "1", path: "/media", label: "Label" });
        }),
    );
    let deleteResolve: (value: unknown) => void = () => {};
    (storagePathsApi.delete as any).mockImplementation(
      () =>
        new Promise((resolve) => {
          deleteResolve = resolve;
        }),
    );

    render(<StorageManagerDialog />, { wrapper });
    fireEvent.click(screen.getByTestId("storage-manager-trigger"));
    await waitFor(() => screen.getByText("Label"));

    // Enter edit mode and click save to trigger pending loader
    fireEvent.click(screen.getByLabelText(/edit label for \/media/i));
    const saveBtn = screen.getByLabelText(/save changes/i);
    fireEvent.click(saveBtn);
    await waitFor(() => {
      const updateLoader =
        screen.queryByTestId("icon-loader2") ??
        document.querySelector(".animate-spin");
      expect(updateLoader).toBeTruthy();
    });
    updateResolve();

    // Trigger delete pending loader
    const row = screen.getByText("/media").closest("tr") as HTMLElement;
    const deleteBtn =
      within(row)
        .getAllByRole("button")
        .find((btn) => !btn.ariaLabel) ??
      within(row).getAllByRole("button").slice(-1)[0];
    fireEvent.click(deleteBtn);
    await waitFor(() =>
      expect(document.querySelector(".animate-spin")).toBeTruthy(),
    );
    deleteResolve(undefined);
  });

  describe("Branch Coverage - Additional Error Handling and Edge Cases", () => {
    it("handles create error with object detail.message", async () => {
      (storagePathsApi.getAll as any).mockResolvedValue([]);
      (storagePathsApi.create as any).mockRejectedValue({
        response: { data: { detail: { message: "Object message" } } },
      });
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      const input = await screen.findByPlaceholderText("/path/to/media");
      fireEvent.change(input, { target: { value: "/foo" } });
      fireEvent.click(screen.getByRole("button", { name: /add/i }));
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          "Error adding path",
          expect.objectContaining({ description: "Object message" }),
        ),
      );
    });

    it("handles create error with no detail (fallback to error.message)", async () => {
      (storagePathsApi.getAll as any).mockResolvedValue([]);
      (storagePathsApi.create as any).mockRejectedValue(
        new Error("Generic error"),
      );
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      const input = await screen.findByPlaceholderText("/path/to/media");
      fireEvent.change(input, { target: { value: "/bar" } });
      fireEvent.click(screen.getByRole("button", { name: /add/i }));
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          "Error adding path",
          expect.objectContaining({ description: "Generic error" }),
        ),
      );
    });

    it("handles create error with absolute fallback message", async () => {
      (storagePathsApi.getAll as any).mockResolvedValue([]);
      const error = new Error("");
      (error as any).message = "";
      (storagePathsApi.create as any).mockRejectedValue(error);
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      const input = await screen.findByPlaceholderText("/path/to/media");
      fireEvent.change(input, { target: { value: "/fallback" } });
      fireEvent.click(screen.getByRole("button", { name: /add/i }));
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          "Error adding path",
          expect.objectContaining({ description: "Failed to add path" }),
        ),
      );
    });

    it("handles delete error with string detail", async () => {
      const mockPaths = [{ id: "del-1", path: "/del", label: "Del" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      (storagePathsApi.delete as any).mockRejectedValue({
        response: { data: { detail: "String error" } },
      });
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("/del"));
      const row = screen.getByText("/del").closest("tr") as HTMLElement;
      const deleteBtn = within(row).getAllByRole("button").pop()!;
      fireEvent.click(deleteBtn);
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith("String error"),
      );
    });

    it("handles delete error with object detail.message", async () => {
      const mockPaths = [{ id: "del-2", path: "/del2", label: "Del2" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      (storagePathsApi.delete as any).mockRejectedValue({
        response: { data: { detail: { message: "Nested delete" } } },
      });
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("/del2"));
      const row = screen.getByText("/del2").closest("tr") as HTMLElement;
      const deleteBtn = within(row).getAllByRole("button").pop()!;
      fireEvent.click(deleteBtn);
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith("Nested delete"),
      );
    });

    it("handles delete error with no detail (fallback to error.message)", async () => {
      const mockPaths = [{ id: "del-3", path: "/del3", label: "Del3" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      (storagePathsApi.delete as any).mockRejectedValue(
        new Error("Default delete"),
      );
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("/del3"));
      const row = screen.getByText("/del3").closest("tr") as HTMLElement;
      const deleteBtn = within(row).getAllByRole("button").pop()!;
      fireEvent.click(deleteBtn);
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith("Default delete"),
      );
    });

    it("handles delete error with absolute fallback message", async () => {
      const mockPaths = [{ id: "del-4", path: "/del4", label: "Del4" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      const error = new Error("");
      (error as any).message = "";
      (storagePathsApi.delete as any).mockRejectedValue(error);
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("/del4"));
      const row = screen.getByText("/del4").closest("tr") as HTMLElement;
      const deleteBtn = within(row).getAllByRole("button").pop()!;
      fireEvent.click(deleteBtn);
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith("Failed to remove path"),
      );
    });

    it("handles update error with no detail (fallback to error.message)", async () => {
      const mockPaths = [{ id: "upd-1", path: "/upd", label: "Old" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      (storagePathsApi.update as any).mockRejectedValue(
        new Error("Update fallback"),
      );
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("Old"));
      fireEvent.click(screen.getByLabelText(/edit label for \/upd/i));
      const input = screen.getByPlaceholderText("Path label...");
      fireEvent.change(input, { target: { value: "New" } });
      fireEvent.click(screen.getByLabelText(/save changes/i));
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith("Update fallback"),
      );
    });

    it("handles update error with absolute fallback message", async () => {
      const mockPaths = [{ id: "upd-2", path: "/upd2", label: "Old2" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      const error = new Error("");
      (error as any).message = "";
      (storagePathsApi.update as any).mockRejectedValue(error);
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("Old2"));
      fireEvent.click(screen.getByLabelText(/edit label for \/upd2/i));
      const input = screen.getByPlaceholderText("Path label...");
      fireEvent.change(input, { target: { value: "New2" } });
      fireEvent.click(screen.getByLabelText(/save changes/i));
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith("Failed to update path"),
      );
    });

    it("verifies delete button is disabled and shows loader when pending", async () => {
      const mockPaths = [{ id: "pend-1", path: "/pend", label: "Pend" }];
      (storagePathsApi.getAll as any).mockResolvedValue(mockPaths);
      let resolveDelete: (value: unknown) => void = () => {};
      (storagePathsApi.delete as any).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveDelete = resolve;
          }),
      );
      render(<StorageManagerDialog />, { wrapper });
      fireEvent.click(screen.getByTestId("storage-manager-trigger"));
      await waitFor(() => screen.getByText("/pend"));
      const row = screen.getByText("/pend").closest("tr") as HTMLElement;
      const deleteBtn = within(row)
        .getAllByRole("button")
        .pop() as HTMLButtonElement;
      fireEvent.click(deleteBtn);
      await waitFor(() => {
        expect(deleteBtn.disabled).toBe(true);
        expect(deleteBtn.querySelector(".animate-spin")).toBeTruthy();
      });
      resolveDelete(undefined);
      await waitFor(() => expect(deleteBtn.disabled).toBe(false));
    });
  });
});
