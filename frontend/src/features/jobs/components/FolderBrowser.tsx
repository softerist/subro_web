import { MouseEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Download,
  FolderOpen,
  FolderPlus,
  Home,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

import { jobsApi } from "../api/jobs";
import { storagePathsApi } from "../api/storagePaths";
import { CompletedTorrent, FolderBrowserEntry } from "../types";
import { useAuthStore } from "@/store/authStore";

interface FolderBrowserProps {
  value: string;
  onChange: (path: string) => void;
}

interface SelectedDisplay {
  path: string;
  label: string;
}

interface ApiError extends Error {
  response?: {
    status?: number;
    data?: {
      detail?:
        | string
        | {
            code?: string;
            message?: string;
          };
    };
  };
}

type BrowserMode = "allowed" | "external";

function getPathLeaf(path: string): string {
  const segments = path.split(/[\\/]+/).filter(Boolean);
  return segments.at(-1) || path;
}

function isDuplicatePathError(error: ApiError): boolean {
  const detail = error.response?.data?.detail;
  return typeof detail !== "string" && detail?.code === "PATH_ALREADY_EXISTS";
}

function getApiErrorMessage(error: ApiError, fallback: string): string {
  const detail = error.response?.data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  return detail?.message || error.message || fallback;
}

function isSystemRootPath(path: string): boolean {
  return path === "/" || /^[A-Za-z]:[\\/]*$/.test(path);
}

function getDefaultStorageLabel(path: string): string {
  return `Custom: ${getPathLeaf(path)}`;
}

export function FolderBrowser({ value, onChange }: FolderBrowserProps) {
  const { accessToken, user } = useAuthStore((state) => ({
    accessToken: state.accessToken,
    user: state.user,
  }));
  const queryClient = useQueryClient();
  const isSuperuser = user?.is_superuser === true;

  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<BrowserMode>("allowed");
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [pathStack, setPathStack] = useState<string[]>([]);
  const [selectedDisplay, setSelectedDisplay] =
    useState<SelectedDisplay | null>(null);
  const [pendingExternalPath, setPendingExternalPath] = useState<string | null>(
    null,
  );

  useEffect(() => {
    if (!value) {
      setSelectedDisplay(null);
      return;
    }

    setSelectedDisplay((prev) => (prev?.path === value ? prev : null));
  }, [value]);

  const resetBrowser = useCallback(() => {
    setMode("allowed");
    setCurrentPath(null);
    setPathStack([]);
    setPendingExternalPath(null);
  }, []);

  const handleOpenChange = useCallback(
    (isOpen: boolean) => {
      setOpen(isOpen);
      if (isOpen) {
        resetBrowser();
      }
    },
    [resetBrowser],
  );

  const folderQuery = useQuery({
    queryKey: ["folder-browser", mode, currentPath ?? "__roots__"],
    queryFn: async (): Promise<FolderBrowserEntry[]> => {
      if (mode === "external") {
        return storagePathsApi.browseSystemFolders(currentPath ?? undefined);
      }

      return storagePathsApi.browseFolders(currentPath ?? undefined);
    },
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    enabled: open && !!accessToken && (mode !== "external" || isSuperuser),
    refetchOnMount: "always" as const,
  });

  const { data: recentTorrents, isLoading: isLoadingTorrents } = useQuery({
    queryKey: ["recent-torrents"],
    queryFn: jobsApi.getRecentTorrents,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    enabled:
      !!accessToken && open && currentPath === null && mode === "allowed",
  });

  const folderEntries = folderQuery.data ?? [];
  const folderError = folderQuery.error as ApiError | null;

  useEffect(() => {
    if (
      mode === "external" &&
      folderQuery.isError &&
      folderError?.response?.status === 403
    ) {
      toast.error("Session expired or superuser access required");
      resetBrowser();
    }
  }, [folderError, folderQuery.isError, mode, resetBrowser]);

  const torrentPaths = useMemo(
    () =>
      (recentTorrents ?? [])
        .filter((torrent) => !!(torrent.content_path || torrent.save_path))
        .slice()
        .sort((left, right) => {
          const leftTs = left.completed_on
            ? new Date(left.completed_on).getTime()
            : 0;
          const rightTs = right.completed_on
            ? new Date(right.completed_on).getTime()
            : 0;
          return rightTs - leftTs;
        }),
    [recentTorrents],
  );

  const handleNavigateToPath = useCallback(
    (path: string) => {
      setPendingExternalPath(null);
      setPathStack((prev) => [
        ...prev,
        ...(currentPath !== null ? [currentPath] : []),
      ]);
      setCurrentPath(path);
    },
    [currentPath],
  );

  const handleBrowseClick = useCallback(
    (event: MouseEvent<HTMLButtonElement>, entry: FolderBrowserEntry) => {
      event.preventDefault();
      event.stopPropagation();
      handleNavigateToPath(entry.path);
    },
    [handleNavigateToPath],
  );

  const handleSelectFolder = useCallback(
    (path: string, label = path) => {
      setSelectedDisplay({ path, label });
      onChange(path);
      setOpen(false);
    },
    [onChange],
  );

  const addAllowedPathMutation = useMutation({
    mutationFn: (path: string) =>
      storagePathsApi.create({
        path,
        label: getDefaultStorageLabel(path),
      }),
    onSuccess: (_, path) => {
      setPendingExternalPath(null);
      queryClient.invalidateQueries({ queryKey: ["storage-paths"] });
      queryClient.invalidateQueries({ queryKey: ["folder-browser"] });
      handleSelectFolder(path, path);
    },
    onError: (error: ApiError, path) => {
      if (isDuplicatePathError(error)) {
        setPendingExternalPath(null);
        queryClient.invalidateQueries({ queryKey: ["storage-paths"] });
        queryClient.invalidateQueries({ queryKey: ["folder-browser"] });
        handleSelectFolder(path, path);
        return;
      }

      toast.error("Failed to allow folder", {
        description: getApiErrorMessage(
          error,
          "Unable to add this folder to allowed paths.",
        ),
      });
    },
  });

  const handleBreadcrumbNav = useCallback(
    (index: number) => {
      setPendingExternalPath(null);
      if (index === -1) {
        setCurrentPath(null);
        setPathStack([]);
        return;
      }

      const targetPath = pathStack[index];
      setCurrentPath(targetPath);
      setPathStack((prev) => prev.slice(0, index));
    },
    [pathStack],
  );

  const handleNavigateBack = useCallback(() => {
    setPendingExternalPath(null);
    if (pathStack.length === 0) {
      setCurrentPath(null);
      return;
    }

    setCurrentPath(pathStack[pathStack.length - 1]);
    setPathStack((prev) => prev.slice(0, -1));
  }, [pathStack]);

  const handleEnterExternalMode = useCallback(() => {
    setMode("external");
    setCurrentPath(null);
    setPathStack([]);
    setPendingExternalPath(null);
  }, []);

  const handleCancelExternalConfirm = useCallback(() => {
    setPendingExternalPath(null);
  }, []);

  const displayValue =
    selectedDisplay?.path === value
      ? selectedDisplay.label
      : value
        ? getPathLeaf(value)
        : null;

  const displayTitle =
    selectedDisplay?.path === value ? selectedDisplay.label : value;

  const hasVisibleMatch =
    folderEntries.some((entry) => entry.path === value) ||
    torrentPaths.some(
      (torrent) => (torrent.content_path || torrent.save_path) === value,
    );
  const shouldShowSelectedPathBadge =
    mode === "allowed" && currentPath === null && !!value && !hasVisibleMatch;
  const isLoadingFolders = folderQuery.isLoading;
  const isFolderError = folderQuery.isError;
  const currentPathIsSystemRoot =
    !!currentPath && isSystemRootPath(currentPath);
  const shouldUseBrowserListScroller =
    mode === "external" || currentPath !== null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="w-full justify-start h-9 text-left font-normal"
          data-testid="folder-browser-trigger"
        >
          {displayValue ? (
            <div className="flex items-center gap-2 min-w-0 w-full">
              <FolderOpen className="h-4 w-4 shrink-0 text-blue-500" />
              <span className="truncate flex-1 min-w-0" title={displayTitle}>
                {displayValue}
              </span>
            </div>
          ) : (
            <span className="text-muted-foreground">Select a folder...</span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[550px] max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Select Folder</DialogTitle>
          <DialogDescription>
            {mode === "external"
              ? "Browse the server filesystem and allow a new target folder."
              : "Browse and select a target folder for the job."}
          </DialogDescription>
        </DialogHeader>

        {shouldShowSelectedPathBadge && (
          <div className="rounded-md border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-xs text-muted-foreground">
            Current selection:
            <span className="ml-1 font-mono text-foreground">{value}</span>
          </div>
        )}

        {currentPath !== null && (
          <div className="space-y-2">
            <div className="flex items-center gap-1 text-xs text-muted-foreground overflow-x-auto pb-1">
              <button
                type="button"
                onClick={() => handleBreadcrumbNav(-1)}
                className="flex items-center gap-1 hover:text-foreground transition-colors shrink-0"
              >
                <Home className="h-3 w-3" />
                {mode === "external" ? "System Roots" : "Roots"}
              </button>
              {pathStack.map((path, index) => (
                <span key={path} className="flex items-center gap-1 shrink-0">
                  <ChevronRight className="h-3 w-3" />
                  <button
                    type="button"
                    onClick={() => handleBreadcrumbNav(index)}
                    className="hover:text-foreground transition-colors"
                  >
                    {getPathLeaf(path)}
                  </button>
                </span>
              ))}
              <span className="flex items-center gap-1 shrink-0">
                <ChevronRight className="h-3 w-3" />
                <span className="text-foreground font-medium">
                  {getPathLeaf(currentPath)}
                </span>
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-mono truncate">
              {currentPath}
            </p>
          </div>
        )}

        <div className="flex-1 min-h-0">
          <div className="space-y-0.5 pr-1 h-full">
            {isLoadingFolders || isLoadingTorrents ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : isFolderError ? (
              <div className="text-center py-8 text-sm text-destructive">
                Failed to load folders
              </div>
            ) : (
              <>
                {currentPath !== null && (
                  <button
                    type="button"
                    onClick={handleNavigateBack}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-accent transition-colors"
                    data-testid="navigate-back"
                  >
                    <ArrowLeft className="h-4 w-4 shrink-0" />
                    <span>Back</span>
                  </button>
                )}

                {currentPath !== null && mode === "allowed" && (
                  <button
                    type="button"
                    onClick={() => handleSelectFolder(currentPath, currentPath)}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm bg-blue-500/10 border border-blue-500/30 hover:bg-blue-500/20 text-blue-500 transition-colors mb-2"
                    data-testid="select-current-folder"
                  >
                    <Check className="h-4 w-4 shrink-0" />
                    <span className="truncate flex-1 min-w-0 text-left">
                      Select This Folder
                    </span>
                    <span className="text-[10px] text-blue-400/70 shrink-0 font-mono">
                      {getPathLeaf(currentPath)}
                    </span>
                  </button>
                )}

                {currentPath !== null && mode === "external" && (
                  <div className="space-y-2 mb-2">
                    <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3">
                      <Button
                        type="button"
                        onClick={() => setPendingExternalPath(currentPath)}
                        disabled={
                          currentPathIsSystemRoot ||
                          addAllowedPathMutation.isPending
                        }
                        className="w-full"
                        data-testid="allow-and-select-current-folder"
                      >
                        {addAllowedPathMutation.isPending &&
                        pendingExternalPath === currentPath ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                          <FolderPlus className="mr-2 h-4 w-4" />
                        )}
                        Allow and Select This Folder
                      </Button>
                      {currentPathIsSystemRoot && (
                        <p className="mt-2 text-xs text-muted-foreground">
                          System roots cannot be added as allowed folders.
                        </p>
                      )}
                    </div>

                    {pendingExternalPath === currentPath &&
                      !currentPathIsSystemRoot && (
                        <div
                          className="rounded-md border border-border bg-muted/40 p-3 space-y-3"
                          data-testid="external-confirmation"
                        >
                          <p className="text-sm text-foreground">
                            Add this folder to allowed paths and use it for the
                            job?
                          </p>
                          <p className="text-xs font-mono text-muted-foreground break-all">
                            {currentPath}
                          </p>
                          <div className="flex gap-2">
                            <Button
                              type="button"
                              size="sm"
                              onClick={() =>
                                addAllowedPathMutation.mutate(currentPath)
                              }
                              disabled={addAllowedPathMutation.isPending}
                              data-testid="confirm-allow-and-select"
                            >
                              {addAllowedPathMutation.isPending ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <Check className="mr-2 h-4 w-4" />
                              )}
                              Confirm
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={handleCancelExternalConfirm}
                              disabled={addAllowedPathMutation.isPending}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}
                  </div>
                )}

                {currentPath === null && mode === "allowed" && (
                  <div className="grid gap-3 min-h-0">
                    <div className="rounded-lg border border-border/70 bg-muted/20">
                      <div className="px-3 py-2 border-b border-border/70 text-xs font-semibold text-muted-foreground flex items-center gap-1">
                        <Download className="h-3 w-3" />
                        Recent Torrents
                      </div>
                      <div className="max-h-56 overflow-y-auto px-1 py-1">
                        {torrentPaths.length > 0 ? (
                          torrentPaths.map(
                            (torrent: CompletedTorrent, index) => {
                              const torrentPath =
                                torrent.content_path || torrent.save_path;
                              const isSelected = torrentPath === value;

                              return (
                                <button
                                  type="button"
                                  key={`torrent-${torrentPath}-${torrent.completed_on ?? index}`}
                                  onClick={() =>
                                    handleSelectFolder(
                                      torrentPath,
                                      torrent.name,
                                    )
                                  }
                                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                                    isSelected
                                      ? "bg-blue-500/10 border border-blue-500/20"
                                      : "hover:bg-accent"
                                  }`}
                                >
                                  <Download className="h-4 w-4 shrink-0 text-blue-500" />
                                  <span
                                    className="truncate flex-1 min-w-0 text-left"
                                    title={torrent.name}
                                  >
                                    {torrent.name}
                                  </span>
                                </button>
                              );
                            },
                          )
                        ) : (
                          <div className="px-3 py-4 text-sm text-muted-foreground">
                            No recent torrents found
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="rounded-lg border border-border/70 bg-muted/20">
                      <div className="px-3 py-2 border-b border-border/70 space-y-1">
                        <div className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
                          <FolderOpen className="h-3 w-3" />
                          Allowed Folders
                        </div>
                        <p className="text-[11px] text-muted-foreground/80">
                          Select a folder directly, or use Browse to navigate
                          into a subfolder before selecting it.
                        </p>
                      </div>

                      {isSuperuser && (
                        <div className="px-3 pt-3">
                          <Button
                            type="button"
                            variant="outline"
                            className="w-full justify-start border-dashed"
                            onClick={handleEnterExternalMode}
                            data-testid="browse-other-folders"
                          >
                            <FolderPlus className="mr-2 h-4 w-4" />
                            Browse Other Folders
                          </Button>
                        </div>
                      )}

                      <div className="max-h-56 overflow-y-auto px-1 py-3">
                        {folderEntries.length > 0 ? (
                          folderEntries.map((entry) => {
                            const isSelected = entry.path === value;

                            return (
                              <div
                                key={entry.path}
                                className={`flex items-center rounded-md transition-colors ${
                                  isSelected
                                    ? "bg-blue-500/10 border border-blue-500/20"
                                    : "hover:bg-accent"
                                }`}
                              >
                                <button
                                  type="button"
                                  onClick={() =>
                                    handleSelectFolder(entry.path, entry.path)
                                  }
                                  className="flex-1 flex items-center gap-2 px-3 py-2 text-sm min-w-0"
                                  title={`Select ${entry.path}`}
                                >
                                  <FolderOpen className="h-4 w-4 shrink-0 text-amber-500/80" />
                                  <span className="truncate flex-1 min-w-0 text-left">
                                    {entry.name}
                                  </span>
                                </button>
                                {entry.has_children && (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={(event) =>
                                      handleBrowseClick(event, entry)
                                    }
                                    className="mr-1 h-8 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground shrink-0"
                                    title={`Browse into ${entry.name}`}
                                    data-testid={`browse-${entry.name}`}
                                  >
                                    Browse
                                    <ChevronRight className="h-3.5 w-3.5" />
                                  </Button>
                                )}
                              </div>
                            );
                          })
                        ) : (
                          <div className="px-3 py-4 text-sm text-muted-foreground space-y-1">
                            <div>No allowed folders found</div>
                            <div className="text-xs">
                              Add a path in storage management to start
                              selecting job targets.
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {shouldUseBrowserListScroller && (
                  <div
                    className="max-h-[50vh] overflow-y-auto space-y-0.5 pr-1"
                    data-testid="folder-browser-list-scroll"
                  >
                    {folderEntries.length === 0 &&
                      currentPath === null &&
                      mode === "external" && (
                        <div className="text-center py-6 text-sm text-muted-foreground">
                          No filesystem roots available
                        </div>
                      )}

                    {folderEntries.length === 0 && currentPath !== null && (
                      <div className="text-center py-6 text-sm text-muted-foreground">
                        No subfolders found
                      </div>
                    )}

                    {folderEntries.map((entry) => {
                      const isSelected = entry.path === value;

                      if (mode === "external") {
                        return (
                          <button
                            type="button"
                            key={entry.path}
                            onClick={() => handleNavigateToPath(entry.path)}
                            className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                              isSelected
                                ? "bg-blue-500/10 border border-blue-500/20"
                                : "hover:bg-accent"
                            }`}
                            title={`Browse ${entry.path}`}
                          >
                            <FolderOpen className="h-4 w-4 shrink-0 text-amber-500/80" />
                            <span className="truncate flex-1 min-w-0 text-left">
                              {entry.name}
                            </span>
                            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                          </button>
                        );
                      }

                      return (
                        <div
                          key={entry.path}
                          className={`flex items-center rounded-md transition-colors ${
                            isSelected
                              ? "bg-blue-500/10 border border-blue-500/20"
                              : "hover:bg-accent"
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() =>
                              handleSelectFolder(entry.path, entry.path)
                            }
                            className="flex-1 flex items-center gap-2 px-3 py-2 text-sm min-w-0"
                            title={`Select ${entry.path}`}
                          >
                            <FolderOpen className="h-4 w-4 shrink-0 text-amber-500/80" />
                            <span className="truncate flex-1 min-w-0 text-left">
                              {entry.name}
                            </span>
                          </button>
                          {entry.has_children && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={(event) =>
                                handleBrowseClick(event, entry)
                              }
                              className="mr-1 h-8 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground shrink-0"
                              title={`Browse into ${entry.name}`}
                              data-testid={`browse-${entry.name}`}
                            >
                              Browse
                              <ChevronRight className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
