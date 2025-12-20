import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, FolderOpen } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
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
import { Input } from "@/components/ui/input";

import { jobsApi } from "../api/jobs";

// Validation Schema
const formSchema = z.object({
  folder_path: z.string().min(1, "Target folder is required"),
  language: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

export function JobForm() {
  const queryClient = useQueryClient();

  // Fetch Allowed Folders from API
  const { data: allowedFolders, isLoading: isLoadingFolders } = useQuery({
    queryKey: ["allowed-folders"],
    queryFn: jobsApi.getAllowedFolders,
  });

  // Setup Form
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      folder_path: "",
      language: "eng",
    },
  });

  // Create Job Mutation
  const mutation = useMutation({
    mutationFn: jobsApi.create,
    onSuccess: () => {
      toast.success("Job started successfully");
      form.reset();
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
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
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <FormField
          control={form.control}
          name="folder_path"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Target Folder</FormLabel>
              <Select onValueChange={field.onChange} defaultValue={field.value}>
                <FormControl>
                  <SelectTrigger>
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
              <FormDescription>
                The folder on the server where subtitles will be downloaded.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FormField
            control={form.control}
            name="language"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Language Code (ISO 639-2)</FormLabel>
                <FormControl>
                  <Input placeholder="eng" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending && (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          )}
          Start Job
        </Button>
      </form>
    </Form>
  );
}
