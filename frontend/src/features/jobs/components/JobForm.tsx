import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, FolderOpen } from "lucide-react";
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
// Removed Input import as it is no longer used
// import { Input } from "@/components/ui/input";

import { jobsApi } from "../api/jobs";
import { LANGUAGES } from "../constants/languages";
import { useAuthStore } from "@/store/authStore";

// Validation Schema
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

  // Fetch Allowed Folders from API (with error suppression since endpoint may not exist)
  const { data: allowedFolders, isLoading: isLoadingFolders } = useQuery({
    queryKey: ["allowed-folders"],
    queryFn: jobsApi.getAllowedFolders,
    retry: false, // Don't retry on failure
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    refetchOnWindowFocus: false,
    enabled: !!accessToken,
  });

  // Setup Form
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      folder_path: "",
      language: "ro",
      log_level: "INFO",
    },
  });

  // Create Job Mutation
  const mutation = useMutation({
    mutationFn: jobsApi.create,
    onSuccess: () => {
      toast.success("Job started successfully");
      form.reset();
      // queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(
        `Failed to start job: ${error.response?.data?.detail || error.message}`,
      );
    },
  });

  const onSubmit = (values: FormValues) => {
    mutation.mutate(values);
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-2">
        <FormField
          control={form.control}
          name="folder_path"
          render={({ field }) => (
            <FormItem className="space-y-0.5">
              <FormLabel>Target Folder</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="Select a folder..." />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {isLoadingFolders ? (
                    <div className="p-2 text-center text-sm text-muted-foreground">
                      Loading folders...
                    </div>
                  ) : (
                    allowedFolders?.map((folder) => (
                      <SelectItem key={folder} value={folder}>
                        <div className="flex items-center gap-2">
                          <FolderOpen className="h-4 w-4" />
                          {folder}
                        </div>
                      </SelectItem>
                    ))
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
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger className="h-9">
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
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger className="h-9">
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
