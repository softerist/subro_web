import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FolderOpen,
  ChevronRight,
  Loader2,
  Download,
  Home,
  Check,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";

import { storagePathsApi } from "../api/storagePaths";
import { jobsApi } from "../api/jobs";
import { useAuthStore } from "@/store/authStore";
import { FolderBrowserEntry, CompletedTorrent } from "../types";

interface FolderBrowserProps {
  value: string;
  onChange: (path: string) => void;
}

interface SelectedDisplay {
  path: string;
  label: string;
}

function getPathLeaf(path: string): string {
  const segments = path.split(/[\\/]+/).filter(Boolean);
  return segments.at(-1) || path;
}

export function FolderBrowser({ value, onChange }: FolderBrowserProps) {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [open, setOpen] = useState(false);
  // null means "show roots", a string means "browsing that path"
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  // Stack of parent paths for breadcrumb navigation
  const [pathStack, setPathStack] = useState<string[]>([]);
  const [selectedDisplay, setSelectedDisplay] =
    useState<SelectedDisplay | null>(null);

  useEffect(() => {
    if (!value) {
      setSelectedDisplay(null);
      return;
    }

    setSelectedDisplay((prev) => (prev?.path === value ? prev : null));
  }, [value]);

  const resetBrowser = useCallback(() => {
    setCurrentPath(null);
    setPathStack([]);
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

  // Fetch folder entries (roots when currentPath is null, children otherwise)
  const {
    data: folderEntries,
    isLoading: isLoadingFolders,
    isError: isFolderError,
  } = useQuery({
    queryKey: ["folder-browser", currentPath ?? "__roots__"],
    queryFn: () => storagePathsApi.browseFolders(currentPath ?? undefined),
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    enabled: open && !!accessToken,
    refetchOnMount: "always" as const,
  });

  // Fetch recent torrents when browser is open
  const { data: recentTorrents, isLoading: isLoadingTorrents } = useQuery({
    queryKey: ["recent-torrents"],
    queryFn: jobsApi.getRecentTorrents,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    enabled: !!accessToken && open && currentPath === null,
  });

  const torrentPaths = recentTorrents
    ? Array.from(
        new Map(
          recentTorrents.map((t: CompletedTorrent) => [
            t.content_path || t.save_path,
            t,
          ]),
        ).values(),
      )
    : [];

  const handleDrillDown = useCallback(
    (entry: FolderBrowserEntry) => {
      setPathStack((prev) => [
        ...prev,
        ...(currentPath !== null ? [currentPath] : []),
      ]);
      setCurrentPath(entry.path);
    },
    [currentPath],
  );

  const handleSelectFolder = useCallback(
    (path: string, label = path) => {
      setSelectedDisplay({ path, label });
      onChange(path);
      setOpen(false);
    },
    [onChange],
  );

  const handleBreadcrumbNav = useCallback(
    (index: number) => {
      if (index === -1) {
        // Go to roots
        setCurrentPath(null);
        setPathStack([]);
      } else {
        const targetPath = pathStack[index];
        setCurrentPath(targetPath);
        setPathStack((prev) => prev.slice(0, index));
      }
    },
    [pathStack],
  );

  const displayValue =
    selectedDisplay?.path === value
      ? selectedDisplay.label
      : value
        ? getPathLeaf(value)
        : null;

  const displayTitle =
    selectedDisplay?.path === value ? selectedDisplay.label : value;

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
            Browse and select a target folder for the job.
          </DialogDescription>
        </DialogHeader>

        {/* Breadcrumb */}
        {currentPath !== null && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground overflow-x-auto pb-1">
            <button
              type="button"
              onClick={() => handleBreadcrumbNav(-1)}
              className="flex items-center gap-1 hover:text-foreground transition-colors shrink-0"
            >
              <Home className="h-3 w-3" />
              Roots
            </button>
            {pathStack.map((p, i) => {
              const name = getPathLeaf(p);
              return (
                <span key={p} className="flex items-center gap-1 shrink-0">
                  <ChevronRight className="h-3 w-3" />
                  <button
                    type="button"
                    onClick={() => handleBreadcrumbNav(i)}
                    className="hover:text-foreground transition-colors"
                  >
                    {name}
                  </button>
                </span>
              );
            })}
            <span className="flex items-center gap-1 shrink-0">
              <ChevronRight className="h-3 w-3" />
              <span className="text-foreground font-medium">
                {getPathLeaf(currentPath)}
              </span>
            </span>
          </div>
        )}

        <ScrollArea className="flex-1 max-h-[50vh]">
          <div className="space-y-0.5 pr-3">
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
                {/* Current folder select button (when browsing) */}
                {currentPath !== null && (
                  <button
                    type="button"
                    onClick={() => handleSelectFolder(currentPath, currentPath)}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm
                      bg-blue-500/10 border border-blue-500/30 hover:bg-blue-500/20
                      text-blue-500 transition-colors mb-2"
                    data-testid="select-current-folder"
                  >
                    <Check className="h-4 w-4 shrink-0" />
                    <span className="truncate flex-1 min-w-0 text-left">
                      Select this folder
                    </span>
                    <span className="text-[10px] text-blue-400/70 shrink-0 font-mono">
                      {getPathLeaf(currentPath)}
                    </span>
                  </button>
                )}

                {/* Recent Torrents (only on root view) */}
                {currentPath === null && torrentPaths.length > 0 && (
                  <>
                    <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground flex items-center gap-1">
                      <Download className="h-3 w-3" />
                      Recent Torrents
                    </div>
                    {torrentPaths.map((torrent: CompletedTorrent) => {
                      const torrentPath =
                        torrent.content_path || torrent.save_path;
                      return (
                        <button
                          type="button"
                          key={`torrent-${torrentPath}`}
                          onClick={() =>
                            handleSelectFolder(torrentPath, torrent.name)
                          }
                          className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm
                            hover:bg-accent transition-colors"
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
                    })}
                    <div className="my-1.5 border-t border-border" />
                  </>
                )}

                {/* Folder entries */}
                {currentPath === null && (folderEntries?.length ?? 0) > 0 && (
                  <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground flex items-center gap-1">
                    <FolderOpen className="h-3 w-3" />
                    Allowed Folders
                  </div>
                )}

                {(folderEntries?.length ?? 0) === 0 &&
                  currentPath === null &&
                  torrentPaths.length === 0 && (
                    <div className="text-center py-6 text-sm text-muted-foreground">
                      No allowed folders found
                    </div>
                  )}

                {(folderEntries?.length ?? 0) === 0 && currentPath !== null && (
                  <div className="text-center py-6 text-sm text-muted-foreground">
                    No subfolders found
                  </div>
                )}

                {folderEntries?.map((entry) => (
                  <div
                    key={entry.path}
                    className="flex items-center rounded-md hover:bg-accent transition-colors"
                  >
                    <button
                      type="button"
                      onClick={() => handleSelectFolder(entry.path, entry.path)}
                      className="flex-1 flex items-center gap-2 px-3 py-2 text-sm min-w-0"
                      title={`Select ${entry.path}`}
                    >
                      <FolderOpen className="h-4 w-4 shrink-0 text-amber-500/80" />
                      <span className="truncate flex-1 min-w-0 text-left">
                        {entry.name}
                      </span>
                    </button>
                    {entry.has_children && (
                      <button
                        type="button"
                        onClick={() => handleDrillDown(entry)}
                        className="px-2 py-2 text-muted-foreground hover:text-foreground transition-colors shrink-0"
                        title={`Browse into ${entry.name}`}
                        data-testid={`browse-${entry.name}`}
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
