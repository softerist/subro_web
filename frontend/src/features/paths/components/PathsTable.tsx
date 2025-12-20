import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { pathsApi } from "../api/paths";
import { useState } from "react";
import { StoragePath } from "../types";

export function PathsTable() {
  const queryClient = useQueryClient();
  const [pathToDelete, setPathToDelete] = useState<StoragePath | null>(null);

  const {
    data: paths,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["storage-paths"],
    queryFn: pathsApi.getAll,
  });

  const deleteMutation = useMutation({
    mutationFn: pathsApi.delete,
    onSuccess: () => {
      toast.success("Path removed successfully");
      queryClient.invalidateQueries({ queryKey: ["storage-paths"] });
      setPathToDelete(null);
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(`Failed to remove path: ${error.message}`);
    },
  });

  const handleDeleteClick = (path: StoragePath) => {
    setPathToDelete(path);
  };

  const confirmDelete = () => {
    if (pathToDelete) {
      deleteMutation.mutate(pathToDelete.id);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return <div className="text-destructive">Failed to load paths.</div>;
  }

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Path</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>Added At</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!paths || paths.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center">
                  No paths configured.
                </TableCell>
              </TableRow>
            ) : (
              paths.map((path) => (
                <TableRow key={path.id}>
                  <TableCell className="font-medium font-mono">
                    {path.path}
                  </TableCell>
                  <TableCell>{path.label || "-"}</TableCell>
                  <TableCell>
                    {format(new Date(path.created_at), "MMM d, yyyy")}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDeleteClick(path)}
                      disabled={
                        deleteMutation.isPending &&
                        deleteMutation.variables === path.id
                      }
                      title="Remove Path"
                    >
                      {deleteMutation.isPending &&
                      deleteMutation.variables === path.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4 text-destructive" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog
        open={!!pathToDelete}
        onOpenChange={(open) => !open && setPathToDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove Path</DialogTitle>
            <DialogDescription>
              Are you sure you want to remove this path? <br />
              <span className="font-mono font-medium text-foreground">
                {pathToDelete?.path}
              </span>
              <br />
              <br />
              This will purely remove it from the allowed list. Use caution.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPathToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                "Remove"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
