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

import { FolderBrowser } from "../features/jobs/components/FolderBrowser";
import { jobsApi } from "../features/jobs/api/jobs";
import { storagePathsApi } from "../features/jobs/api/storagePaths";

vi.mock("../features/jobs/api/storagePaths", () => ({
  storagePathsApi: {
    browseFolders: vi.fn(),
  },
}));

vi.mock("../features/jobs/api/jobs", () => ({
  jobsApi: {
    getRecentTorrents: vi.fn(),
  },
}));

vi.mock("@/store/authStore", () => ({
  useAuthStore: (selector: (state: { accessToken: string | null }) => unknown) =>
    selector({ accessToken: "mock-token" }),
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

function ControlledFolderBrowser() {
  const [value, setValue] = useState("");

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
    (jobsApi.getRecentTorrents as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  });

  it("loads root folders when opened and selects a folder", async () => {
    (storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
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

    expect(screen.getByTestId("folder-browser-trigger")).toHaveTextContent(
      "/media/movies",
    );
  });

  it("renders Windows-style path labels in the trigger and leaf names in the breadcrumb", async () => {
    (storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async (path?: string) => {
        if (!path) {
          return [
            {
              name: "Movies",
              path: "C:\\Media\\Movies",
              has_children: true,
            },
          ];
        }

        return [
          {
            name: "SomeMovie",
            path: "C:\\Media\\Movies\\SomeMovie",
            has_children: false,
          },
        ];
      },
    );

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    await waitFor(() => {
      expect(screen.getByTestId("browse-Movies")).toBeDefined();
    });

    fireEvent.click(await screen.findByTitle("Select C:\\Media\\Movies"));
    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "C:\\Media\\Movies",
      );
    });

    expect(screen.getByTestId("folder-browser-trigger")).toHaveTextContent(
      "C:\\Media\\Movies",
    );

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));
    await waitFor(() => {
      expect(screen.getByTestId("browse-Movies")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("browse-Movies"));
    await waitFor(() => {
      expect(screen.getByTestId("select-current-folder")).toBeDefined();
    });

    expect(screen.getByTestId("select-current-folder")).toHaveTextContent(
      "Movies",
    );
  });

  it("drills into subfolders and can select the current folder", async () => {
    (storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async (path?: string) => {
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
      },
    );

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(screen.getByTestId("browse-movies")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("browse-movies"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledWith(
        "/media/movies",
      );
    });

    fireEvent.click(await screen.findByTestId("select-current-folder"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "/media/movies",
      );
    });

    expect(screen.getByTestId("folder-browser-trigger")).toHaveTextContent(
      "/media/movies",
    );
  });

  it("shows recent torrents at the root and selects them", async () => {
    (storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (jobsApi.getRecentTorrents as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        name: "Movie 1",
        save_path: "/downloads",
        content_path: "/downloads/movie1",
        completed_on: "2023-01-01",
      },
    ]);

    render(<ControlledFolderBrowser />, { wrapper });

    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(screen.getByText("Movie 1")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Movie 1"));

    await waitFor(() => {
      expect(screen.getByTestId("selected-path").textContent).toBe(
        "/downloads/movie1",
      );
    });

    expect(screen.getByTestId("folder-browser-trigger")).toHaveTextContent(
      "Movie 1",
    );
  });

  it("refetches roots every time the browser is opened", async () => {
    (storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
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

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    fireEvent.click(screen.getByTestId("folder-browser-trigger"));

    await waitFor(() => {
      expect(storagePathsApi.browseFolders).toHaveBeenCalledTimes(2);
    });
  });

  it("does not submit a parent form when opening the browser", async () => {
    const onSubmit = vi.fn();
    (storagePathsApi.browseFolders as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([]);

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
});
