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
import { Card } from "@/components/ui/card";
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
      <Card className="soft-hover overflow-hidden border-border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent border-b border-border/40">
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Path
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground hidden sm:table-cell">
                Label
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground hidden md:table-cell">
                Added At
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground text-right">
                Actions
              </TableHead>
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
                  <TableCell className="py-2 font-medium font-mono text-sm">
                    {path.path}
                  </TableCell>
                  <TableCell className="py-2 text-sm hidden sm:table-cell">
                    {path.label || "-"}
                  </TableCell>
                  <TableCell className="py-2 text-sm text-muted-foreground hidden md:table-cell">
                    {format(new Date(path.created_at), "MMM d, yyyy")}
                  </TableCell>
                  <TableCell className="py-2 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDeleteRequest(path)}
                      disabled={
                        deleteMutation.isPending &&
                        confirmState.path?.id === path.id
                      }
                      title="Remove Path"
                      aria-label="Remove path"
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
      </Card>

      <ConfirmDialog
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState((prev) => ({ ...prev, open }))}
        title="Remove Path?"
        description={
          confirmState.path ? (
            <>
              Are you sure you want to remove this path?
              <br />
              <span className="font-mono text-foreground">
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
