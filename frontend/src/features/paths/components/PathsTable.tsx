import { useState } from "react";
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
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

import { pathsApi } from "../api/paths";
import { StoragePath } from "../types";

export function PathsTable() {
  const queryClient = useQueryClient();
  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    path: StoragePath | null;
  }>({ open: false, path: null });

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
      setConfirmState({ open: false, path: null });
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(`Failed to remove path: ${error.message}`);
    },
  });

  const handleDeleteRequest = (path: StoragePath) => {
    setConfirmState({
      open: true,
      path,
    });
  };

  const executeDelete = async () => {
    if (confirmState.path) {
      deleteMutation.mutate(confirmState.path.id);
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
      <div className="rounded-md border soft-hover">
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
                      onClick={() => handleDeleteRequest(path)}
                      disabled={
                        deleteMutation.isPending &&
                        confirmState.path?.id === path.id
                      }
                      title="Remove Path"
                    >
                      {deleteMutation.isPending &&
                      confirmState.path?.id === path.id ? (
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

      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState((prev) => ({ ...prev, open }))}
        title="Remove Path?"
        description={
          confirmState.path ? (
            <>
              Are you sure you want to remove this path?
              <br />
              <span className="font-mono text-white">
                {confirmState.path.path}
              </span>
            </>
          ) : (
            "Are you sure you want to remove this path?"
          )
        }
        onConfirm={executeDelete}
        isLoading={deleteMutation.isPending}
        variant="destructive"
        confirmLabel="Remove"
      />
    </>
  );
}
