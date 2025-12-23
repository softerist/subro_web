import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Loader2, UserCheck, UserX } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { User } from "../types";
import { adminApi } from "../api/admin";

interface UsersTableProps {
  users: User[];
  isLoading: boolean;
}

export function UsersTable({ users, isLoading }: UsersTableProps) {
  const queryClient = useQueryClient();

  // Confirmation dialog state
  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    user: User | null;
    positionY?: number;
  }>({ open: false, user: null });

  const deleteMutation = useMutation({
    mutationFn: adminApi.deleteUser,
    onSuccess: () => {
      toast.success("User deleted successfully");
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setConfirmState({ open: false, user: null });
    },
    onError: (error: Error) => {
      toast.error(`Failed to delete user: ${error.message}`);
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      adminApi.updateUser(id, { is_active: isActive }),
    onSuccess: () => {
      toast.success("User status updated");
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to update user: ${error.message}`);
    },
  });

  const handleDeleteRequest = (user: User, event: React.MouseEvent) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setConfirmState({
      open: true,
      user,
      positionY: rect.top + window.scrollY,
    });
  };

  const executeDelete = async () => {
    if (confirmState.user) {
      deleteMutation.mutate(confirmState.user.id);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center">
                  No users found.
                </TableCell>
              </TableRow>
            ) : (
              users.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.email}</TableCell>
                  <TableCell>
                    <Badge
                      variant={user.is_superuser ? "destructive" : "secondary"}
                    >
                      {user.is_superuser
                        ? "Superuser"
                        : user.role || "standard"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={user.is_active ? "default" : "outline"}>
                      {user.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() =>
                        toggleActiveMutation.mutate({
                          id: user.id,
                          isActive: !user.is_active,
                        })
                      }
                      disabled={toggleActiveMutation.isPending}
                      title={user.is_active ? "Deactivate" : "Activate"}
                    >
                      {user.is_active ? (
                        <UserX className="h-4 w-4 text-orange-500" />
                      ) : (
                        <UserCheck className="h-4 w-4 text-green-500" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => handleDeleteRequest(user, e)}
                      disabled={deleteMutation.isPending}
                      title="Delete User"
                    >
                      {deleteMutation.isPending &&
                      confirmState.user?.id === user.id ? (
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
        title="Delete User?"
        description={
          confirmState.user
            ? `Are you sure you want to delete "${confirmState.user.email}"?`
            : "Are you sure you want to delete this user?"
        }
        onConfirm={executeDelete}
        isLoading={deleteMutation.isPending}
        variant="destructive"
        confirmLabel="Delete"
        positionY={confirmState.positionY}
      />
    </>
  );
}
