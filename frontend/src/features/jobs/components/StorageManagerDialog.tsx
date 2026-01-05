import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Loader2, FolderPlus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

import { storagePathsApi } from "../api/storagePaths";

const formSchema = z.object({
  path: z.string().min(1, "Path is required"),
  label: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

interface ApiError extends Error {
  response?: {
    data?: {
      detail?: string | { message?: string; code?: string };
    };
  };
}

export function StorageManagerDialog() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: paths, isLoading: isLoadingPaths } = useQuery({
    queryKey: ["storage-paths"],
    queryFn: storagePathsApi.getAll,
    enabled: open,
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      path: "",
      label: "",
    },
  });

  const createMutation = useMutation({
    mutationFn: storagePathsApi.create,
    onSuccess: () => {
      toast.success("Path added successfully");
      form.reset();
      queryClient.invalidateQueries({ queryKey: ["storage-paths"] });
      queryClient.invalidateQueries({ queryKey: ["allowed-folders"] }); // Refresh dropdown
    },
    onError: (error: ApiError) => {
      const detail = error.response?.data?.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : detail?.message || error.message || "Failed to add path";
      toast.error("Error adding path", {
        description: msg,
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: storagePathsApi.delete,
    onSuccess: () => {
      toast.success("Path removed successfully");
      queryClient.invalidateQueries({ queryKey: ["storage-paths"] });
      queryClient.invalidateQueries({ queryKey: ["allowed-folders"] });
    },
    onError: (error: ApiError) => {
      const detail = error.response?.data?.detail;
      const msg =
        typeof detail === "string"
          ? detail
          : detail?.message || error.message || "Failed to remove path";
      toast.error(msg);
    },
  });

  const onSubmit = (values: FormValues) => {
    createMutation.mutate({
      path: values.path,
      label: values.label || `Custom: ${values.path.split("/").pop()}`,
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="ml-2 h-9 px-3 border-dashed"
          title="Manage allowed folders"
        >
          <FolderPlus className="h-4 w-4 mr-1" />
          Edit
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Manage Storage Paths</DialogTitle>
          <DialogDescription>
            Add or remove media folders allowed for job processing.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-auto py-4 space-y-6">
          {/* Add Path Form */}
          <div className="rounded-lg border p-4 bg-muted/40">
            <h4 className="text-sm font-medium mb-3">Add New Path</h4>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmit)}
                className="flex items-end gap-3"
              >
                <FormField
                  control={form.control}
                  name="path"
                  render={({ field }) => (
                    <FormItem className="flex-1 space-y-1">
                      <FormLabel className="text-xs">Absolute Path</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="/path/to/media"
                          className="h-8"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button
                  type="submit"
                  size="sm"
                  variant="secondary"
                  className="h-8 shadow-sm"
                  disabled={createMutation.isPending}
                >
                  {createMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4 mr-1" />
                  )}
                  Add
                </Button>
              </form>
            </Form>
          </div>

          {/* Paths Table */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Path</TableHead>
                  <TableHead className="w-[100px]">Type</TableHead>
                  <TableHead className="w-[70px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoadingPaths ? (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center h-24">
                      <Loader2 className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                    </TableCell>
                  </TableRow>
                ) : paths?.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={3}
                      className="text-center h-24 text-muted-foreground"
                    >
                      No paths configured yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  paths?.map((path) => (
                    <TableRow key={path.id}>
                      <TableCell className="font-mono text-xs">
                        {path.path}
                        {path.label && (
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {path.label}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-[10px]">
                          FileSystem
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => deleteMutation.mutate(path.id)}
                          disabled={deleteMutation.isPending}
                        >
                          {deleteMutation.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
