import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { pathsApi } from "../api/paths";

const formSchema = z.object({
  path: z.string().min(1, "Path cannot be empty"),
  label: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

export function AddPathDialog() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      path: "",
      label: "",
    },
  });

  const mutation = useMutation({
    mutationFn: pathsApi.create,
    onSuccess: () => {
      toast.success("Path added successfully");
      setOpen(false);
      form.reset();
      queryClient.invalidateQueries({ queryKey: ["storage-paths"] });
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const msg =
        error.response?.data?.detail || error.message || "Failed to add path";
      toast.error(msg);
    },
  });

  const onSubmit = (values: FormValues) => {
    mutation.mutate(values);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40 transition-all duration-300 border-0">
          <Plus className="mr-2 h-4 w-4" />
          Add Path
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Add Storage Path</DialogTitle>
          <DialogDescription>
            Add a new directory path allowed for subtitle searching/downloading.
            The path must exist on the server.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="path"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Filesystem Path</FormLabel>
                  <FormControl>
                    <Input placeholder="/mnt/media/movies" {...field} />
                  </FormControl>
                  <FormDescription>
                    Absolute path to the media directory.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Label (Optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="Movies Drive" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button
                type="submit"
                disabled={mutation.isPending}
                className="bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40 transition-all duration-300 border-0"
              >
                {mutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Add Path
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
