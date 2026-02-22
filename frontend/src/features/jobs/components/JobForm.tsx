import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, FolderOpen, Download } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { jobsApi } from "../api/jobs";
import { LANGUAGES } from "../constants/languages";
import { useAuthStore } from "@/store/authStore";
import { StorageManagerDialog } from "./StorageManagerDialog";
import { CompletedTorrent } from "../types";

const formSchema = z.object({
  folder_path: z.string().min(1, "Target folder is required"),
  language: z.string().optional(),
  log_level: z.enum(["DEBUG", "INFO", "WARNING", "ERROR"]),
});

type FormValues = z.infer<typeof formSchema>;

const LOG_LEVELS = [
  { value: "DEBUG", label: "Debug (Verbose)" },
  { value: "INFO", label: "Info (Default)" },
  { value: "WARNING", label: "Warning" },
  { value: "ERROR", label: "Error (Minimal)" },
] as const;

export function JobForm() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [isSelectOpen, setIsSelectOpen] = useState(false);

  const jobErrorMessages: Record<string, string> = {
    PATH_NOT_FOUND: "Folder not found on server. Check the path and try again.",
    PATH_INVALID: "Folder path is invalid or cannot be resolved.",
    PATH_NOT_ALLOWED:
      "Folder is not in allowed media folders. Contact an admin to allow it.",
    PATH_AUTO_ADD_FAILED:
      "Server couldn't add this folder to allowed paths. Contact an admin.",
  };

  const resolveJobErrorMessage = (
    detail: string | { code?: string; message?: string } | undefined,
    fallback: string,
  ) => {
    if (typeof detail === "string") {
      return detail;
    }
    if (detail?.code && jobErrorMessages[detail.code]) {
      return jobErrorMessages[detail.code];
    }
    return detail?.message || fallback;
  };

  const { data: allowedFolders, isLoading: isLoadingFolders } = useQuery({
    queryKey: ["allowed-folders"],
    queryFn: jobsApi.getAllowedFolders,
    retry: false,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
    enabled: !!accessToken,
  });

  // Fetch recent torrents when dropdown is opened
  const { data: recentTorrents, isLoading: isLoadingTorrents } = useQuery({
    queryKey: ["recent-torrents"],
    queryFn: jobsApi.getRecentTorrents,
    retry: false,
    staleTime: 0, // Always fetch fresh data when enabled
    refetchOnWindowFocus: false,
    enabled: !!accessToken && isSelectOpen, // Only fetch when dropdown is open
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      folder_path: "",
      language: "ro",
      log_level: "INFO",
    },
  });

  const mutation = useMutation({
    mutationFn: jobsApi.create,
    onSuccess: () => {
      toast.success("Job started successfully");
      form.reset();
    },
    onError: (
      error: Error & {
        response?: {
          data?: { detail?: string | { message?: string; code?: string } };
        };
      },
    ) => {
      const detail = error.response?.data?.detail as
        | string
        | { message?: string; code?: string }
        | undefined;
      const message = resolveJobErrorMessage(detail, error.message);
      toast.error(`Failed to start job: ${message}`);
    },
  });

  const onSubmit = (values: FormValues) => {
    mutation.mutate(values);
  };

  // Get unique save paths from torrents (deduplicated)
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

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-2">
        <FormField
          control={form.control}
          name="folder_path"
          render={({ field }) => (
            <FormItem className="space-y-0.5">
              <div className="flex items-center justify-between">
                <FormLabel>Target Folder</FormLabel>
                <StorageManagerDialog />
              </div>
              <Select
                onValueChange={field.onChange}
                value={field.value}
                name={field.name}
                onOpenChange={setIsSelectOpen}
                data-testid="folder_path"
              >
                <FormControl>
                  <SelectTrigger
                    className="h-9"
                    data-testid="folder-select-trigger"
                  >
                    <SelectValue placeholder="Select a folder..." />
                  </SelectTrigger>
                </FormControl>
                <SelectContent className="w-[var(--radix-select-trigger-width)] max-w-[calc(100vw-2rem)]">
                  {isLoadingFolders || isLoadingTorrents ? (
                    <div className="p-2 text-center text-sm text-muted-foreground">
                      Loading...
                    </div>
                  ) : (
                    <>
                      {/* Recent Torrents Section */}
                      {torrentPaths.length > 0 && (
                        <>
                          <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground flex items-center gap-1">
                            <Download className="h-3 w-3" />
                            Recent Torrents
                          </div>
                          {torrentPaths.map((torrent: CompletedTorrent) => {
                            const torrentPath =
                              torrent.content_path || torrent.save_path;
                            return (
                              <SelectItem
                                key={`torrent-${torrentPath}`}
                                value={torrentPath}
                                className="max-w-full"
                              >
                                <div className="flex items-center gap-2 min-w-0 w-full">
                                  <Download className="h-4 w-4 shrink-0 text-blue-500" />
                                  <span
                                    className="truncate flex-1 min-w-0"
                                    title={torrent.name}
                                  >
                                    {torrent.name}
                                  </span>
                                </div>
                              </SelectItem>
                            );
                          })}
                          <div className="my-1 border-t border-border" />
                        </>
                      )}

                      {/* Allowed Folders Section */}
                      {(allowedFolders?.length ?? 0) > 0 && (
                        <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground flex items-center gap-1">
                          <FolderOpen className="h-3 w-3" />
                          Allowed Folders
                        </div>
                      )}
                      {allowedFolders?.map((folder) => (
                        <SelectItem
                          key={folder}
                          value={folder}
                          className="max-w-full"
                        >
                          <div className="flex items-center gap-2 min-w-0 w-full">
                            <FolderOpen className="h-4 w-4 shrink-0" />
                            <span
                              className="truncate flex-1 min-w-0"
                              title={folder}
                            >
                              {folder}
                            </span>
                          </div>
                        </SelectItem>
                      ))}
                    </>
                  )}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="space-y-2">
          <FormField
            control={form.control}
            name="language"
            render={({ field }) => (
              <FormItem className="space-y-1">
                <FormLabel>Language</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={field.value}
                  name={field.name}
                  data-testid="language"
                >
                  <FormControl>
                    <SelectTrigger
                      className="h-9"
                      data-testid="language-select-trigger"
                    >
                      <SelectValue placeholder="Select language..." />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {LANGUAGES.map((lang) => (
                      <SelectItem key={lang.value} value={lang.value}>
                        {lang.label} ({lang.value})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="log_level"
            render={({ field }) => (
              <FormItem className="space-y-1">
                <FormLabel>Log Level</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={field.value}
                  name={field.name}
                  data-testid="log_level"
                >
                  <FormControl>
                    <SelectTrigger
                      className="h-9"
                      data-testid="log-level-select-trigger"
                    >
                      <SelectValue placeholder="Select log level..." />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {LOG_LEVELS.map((level) => (
                      <SelectItem key={level.value} value={level.value}>
                        {level.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <Button
          type="submit"
          disabled={mutation.isPending}
          className="w-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40 transition-all duration-300 border-0 h-9 mt-1"
        >
          {mutation.isPending && (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          )}
          Start Job
        </Button>
      </form>
    </Form>
  );
}
