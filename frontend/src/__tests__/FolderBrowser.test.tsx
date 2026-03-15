/**
 * @vitest-environment jsdom
 */
import { FormEvent, useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { FolderBrowser } from "../features/jobs/components/FolderBrowser";
import { jobsApi } from "../features/jobs/api/jobs";
import { storagePathsApi } from "../features/jobs/api/storagePaths";

vi.mock("../features/jobs/api/storagePaths", () => ({
  storagePathsApi: {
    browseFolders: vi.fn(),
    browseSystemFolders: vi.fn(),
    create: vi.fn(),
  },
}));

vi.mock("../features/jobs/api/jobs", () => ({
  jobsApi: {
    getRecentTorrents: vi.fn(),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

const mockAuthState = {
  accessToken: "mock-token",
  user: {
    is_superuser: false,
  },
};

vi.mock("@/store/authStore", () => ({
  useAuthStore: (selector: (state: typeof mockAuthState) => unknown) =>
    selector(mockAuthState),
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

function ControlledFolderBrowser({
  initialValue = "",
}: {
  initialValue?: string;
}) {
  const [value, setValue] = useState(initialValue);

  return (
    <>
      <FolderBrowser value={value} onChange={setValue} />
      <div data-testid="selected-path">{value}</div>
    </>
  );
}

window.HTMLElement.prototype.scrollIntoView = vi.fn();
window.HTMLElement.prototype.hasPointerCapture = vi.fn();
window.HTMLElement.prototype.releasePointerCapture = vi.fn();

if (!window.PointerEvent) {
  class PointerEvent extends MouseEvent {
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
    }
  }

  window.PointerEvent = PointerEvent as typeof window.PointerEvent;
}

describe("FolderBrowser", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    queryClient.clear();
    mockAuthState.user.is_superuser = false;
    (
      jobsApi.getRecentTorrents as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      storagePathsApi.browseSystemFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
  });

  it("loads allowed root folders and selects a folder on row click", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([
      {
        name: "movies",
        path: "/media/movies",
        has_children: false,
      },
    ]);

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledWith(undefined);
    });

    fireEvent.click(await screen.findByTitle("Select /media/movies"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "/media/movies",
      );
    });
  });

  it("browses into an allowed folder without selecting the parent and can navigate back", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(async (path?: string) => {
      if (!path) {
        return [
          {
            name: "movies",
            path: "/media/movies",
            has_children: true,
          },
        ];
      }

      return [
        {
          name: "SomeMovie",
          path: "/media/movies/SomeMovie",
          has_children: false,
        },
      ];
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-movies"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledWith(
        "/media/movies",
      );
    });

    expect(screen.getByTestId("selected-path").textContent).toBe("");
    expect(await screen.findByTestId("navigate-back")).toBeDefined();
    expect(
      await screen.findByTestId("select-current-folder"),
    ).toHaveTextContent("movies");

    fireEvent.click(screen.getByTestId("navigate-back"));

    await waitFor(() => {
      expect(screen.getByTestId("browse-movies")).toBeDefined();
    });
  });

  it("selects a child row or the current folder in allowed mode", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(async (path?: string) => {
      if (!path) {
        return [
          {
            name: "movies",
            path: "/media/movies",
            has_children: true,
          },
        ];
      }

      return [
        {
          name: "SomeMovie",
          path: "/media/movies/SomeMovie",
          has_children: true,
        },
        {
          name: "AnotherMovie",
          path: "/media/movies/AnotherMovie",
          has_children: false,
        },
      ];
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-movies"));
    fireEvent.click(await screen.findByTitle("Select /media/movies/SomeMovie"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "/media/movies/SomeMovie",
      );
    });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-movies"));
    fireEvent.click(await screen.findByTestId("select-current-folder"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "/media/movies",
      );
    });
  });

  it("shows recent torrents and selects them from root mode", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      jobsApi.getRecentTorrents as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([
      {
        name: "Movie 1",
        save_path: "/downloads",
        content_path: "/downloads/movie1",
        completed_on: "2023-01-01",
      },
    ]);

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByText("Movie 1"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "/downloads/movie1",
      );
    });
  });

  it("shows Browse Other Folders only for superusers", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);

    render(<ControlledFolderBrowser />, { wrapper });
    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(
        screen.queryByTestId("browse-other-folders"),
      ).not.toBeInTheDocument();
    });

    cleanup();
    queryClient.clear();
    mockAuthState.user.is_superuser = true;

    render(<ControlledFolderBrowser />, { wrapper });
    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(screen.getByTestId("browse-other-folders")).toBeDefined();
    });
  });

  it("lets a superuser browse system folders without selecting on row click", async () => {
    mockAuthState.user.is_superuser = true;
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      storagePathsApi.browseSystemFolders as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(async (path?: string) => {
      if (!path) {
        return [
          {
            name: "/",
            path: "/",
            has_children: true,
          },
        ];
      }

      return [];
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-other-folders"));
    fireEvent.click(await screen.findByTitle("Browse /"));

    await waitFor(() => {
      expect(storagePathsApi.browseSystemFolders).toHaveBeenCalledWith("/");
    });

    expect(screen.getByTestId("selected-path").textContent).toBe("");
    expect(
      await screen.findByTestId("allow-and-select-current-folder"),
    ).toBeDisabled();
    expect(
      screen.getByText("System roots cannot be added as allowed folders."),
    ).toBeInTheDocument();
  });

  it("allows a superuser to confirm, allow, and select an external folder", async () => {
    mockAuthState.user.is_superuser = true;
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      storagePathsApi.browseSystemFolders as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(async (path?: string) => {
      if (!path) {
        return [
          {
            name: "/",
            path: "/",
            has_children: true,
          },
        ];
      }

      if (path === "/") {
        return [
          {
            name: "srv",
            path: "/srv",
            has_children: true,
          },
        ];
      }

      return [];
    });
    (
      storagePathsApi.create as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue({
      id: "1",
      path: "/srv",
      label: "Custom: srv",
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-other-folders"));
    fireEvent.click(await screen.findByTitle("Browse /"));
    fireEvent.click(await screen.findByTitle("Browse /srv"));

    await waitFor(() => {
      expect(storagePathsApi.browseSystemFolders).toHaveBeenCalledWith("/srv");
    });

    fireEvent.click(
      await screen.findByTestId("allow-and-select-current-folder"),
    );
    expect(screen.getByTestId("external-confirmation")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("confirm-allow-and-select"));

    await waitFor(() => {
      expect(storagePathsApi.create).toHaveBeenCalledWith({
        path: "/srv",
        label: "Custom: srv",
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe("/srv");
    });
  });

  it("treats PATH_ALREADY_EXISTS as soft success", async () => {
    mockAuthState.user.is_superuser = true;
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      storagePathsApi.browseSystemFolders as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(async (path?: string) => {
      if (!path) {
        return [
          {
            name: "/",
            path: "/",
            has_children: true,
          },
        ];
      }

      if (path === "/") {
        return [
          {
            name: "srv",
            path: "/srv",
            has_children: false,
          },
        ];
      }

      return [];
    });
    (
      storagePathsApi.create as unknown as ReturnType<typeof vi.fn>
    ).mockRejectedValue({
      response: {
        data: {
          detail: {
            code: "PATH_ALREADY_EXISTS",
            message: "Storage path already exists.",
          },
        },
      },
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-other-folders"));
    fireEvent.click(await screen.findByTitle("Browse /"));
    fireEvent.click(await screen.findByTitle("Browse /srv"));
    fireEvent.click(
      await screen.findByTestId("allow-and-select-current-folder"),
    );
    fireEvent.click(await screen.findByTestId("confirm-allow-and-select"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe("/srv");
    });
  });

  it("keeps the picker open on non-duplicate create errors", async () => {
    mockAuthState.user.is_superuser = true;
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      storagePathsApi.browseSystemFolders as unknown as ReturnType<typeof vi.fn>
    ).mockImplementation(async (path?: string) => {
      if (!path) {
        return [
          {
            name: "/",
            path: "/",
            has_children: true,
          },
        ];
      }

      return [
        {
          name: "srv",
          path: "/srv",
          has_children: false,
        },
      ];
    });
    (
      storagePathsApi.create as unknown as ReturnType<typeof vi.fn>
    ).mockRejectedValue({
      response: {
        data: {
          detail: {
            code: "PATH_INVALID",
            message: "Path invalid",
          },
        },
      },
      message: "Path invalid",
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-other-folders"));
    fireEvent.click(await screen.findByTitle("Browse /"));
    fireEvent.click(await screen.findByTitle("Browse /srv"));
    fireEvent.click(
      await screen.findByTestId("allow-and-select-current-folder"),
    );
    fireEvent.click(await screen.findByTestId("confirm-allow-and-select"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Failed to allow folder",
        expect.objectContaining({
          description: "Path invalid",
        }),
      );
    });

    expect(screen.getByTestId("selected-path").textContent).toBe("");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("falls back to allowed mode when system browse returns 403", async () => {
    mockAuthState.user.is_superuser = true;
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);
    (
      storagePathsApi.browseSystemFolders as unknown as ReturnType<typeof vi.fn>
    ).mockRejectedValue({
      response: {
        status: 403,
      },
    });

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    fireEvent.click(await screen.findByTestId("browse-other-folders"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Session expired or superuser access required",
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("browse-other-folders")).toBeDefined();
    });
  });

  it("shows an empty-state hint and selected path badge when needed", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([
      {
        name: "media",
        path: "/media",
        has_children: true,
      },
    ]);

    render(<ControlledFolderBrowser initialValue="/media/movies/SomeMovie" />, {
      wrapper,
    });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(screen.getByText("Current selection:")).toBeInTheDocument();
    });

    cleanup();
    queryClient.clear();
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);

    render(<ControlledFolderBrowser />, { wrapper });
    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(screen.getByText("No allowed folders found")).toBeInTheDocument();
      expect(
        screen.getByText(/Add a path in storage management/i),
      ).toBeInTheDocument();
    });
  });

  it("does not submit a parent form when opening the browser", async () => {
    const onSubmit = vi.fn();
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([]);

    const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      onSubmit();
    };

    render(
      <form onSubmit={handleSubmit}>
        <FolderBrowser value="" onChange={vi.fn()} />
        <button type="submit">Submit</button>
      </form>,
      { wrapper },
    );

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledWith(undefined);
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("refetches allowed roots when the browser is reopened", async () => {
    (
      storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValue([
      {
        name: "movies",
        path: "/media/movies",
        has_children: false,
      },
    ]);

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledTimes(1);
    });

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledTimes(2);
    });
  });
});
