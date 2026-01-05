import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Loader2, UserCheck, UserX, Key, Pencil } from "lucide-react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { User } from "../types";
import { adminApi } from "../api/admin";
import { useAuthStore } from "@/store/authStore";
import { EditUserDialog } from "./EditUserDialog";

const resetPasswordSchema = z
  .object({
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirmPassword: z.string(),
    forcePasswordChange: z.boolean(),
    disableMFA: z.boolean(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;

interface UsersTableProps {
  users: User[];
  isLoading: boolean;
}

export function UsersTable({ users, isLoading }: UsersTableProps) {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((state) => state.user);

  // Confirmation dialog state
  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    user: User | null;
  }>({ open: false, user: null });

  // Reset Password state
  const [resetState, setResetState] = useState<{
    open: boolean;
    user: User | null;
  }>({ open: false, user: null });

  // Edit User state
  const [editState, setEditState] = useState<{
    open: boolean;
    user: User | null;
  }>({ open: false, user: null });

  const form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: {
      password: "",
      confirmPassword: "",
      forcePasswordChange: true,
      disableMFA: false,
    },
  });

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

  const resetPasswordMutation = useMutation({
    mutationFn: ({
      id,
      password,
      force_password_change,
      mfa_enabled,
    }: {
      id: string;
      password: string;
      force_password_change?: boolean;
      mfa_enabled?: boolean;
    }) =>
      adminApi.updateUser(id, {
        password,
        force_password_change,
        mfa_enabled,
      }),
    onSuccess: () => {
      toast.success("Password reset successfully");
      setResetState({ open: false, user: null });
      form.reset();
    },
    onError: (error: Error) => {
      toast.error(`Failed to reset password: ${error.message}`);
    },
  });

  const handleDeleteRequest = (user: User) => {
    setConfirmState({
      open: true,
      user,
    });
  };

  const handleResetRequest = (user: User) => {
    setResetState({ open: true, user });
    form.reset();
  };

  const handleEditRequest = (user: User) => {
    setEditState({ open: true, user });
  };

  const executeDelete = async () => {
    if (confirmState.user) {
      deleteMutation.mutate(confirmState.user.id);
    }
  };

  const executeReset = (values: ResetPasswordFormValues) => {
    if (resetState.user) {
      resetPasswordMutation.mutate({
        id: resetState.user.id,
        password: values.password,
        force_password_change: values.forcePasswordChange,
        mfa_enabled: values.disableMFA ? false : undefined,
      });
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
      <Card className="soft-hover overflow-hidden border-border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent border-b border-border/40">
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Name
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground">
                Email
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground hidden sm:table-cell">
                Role
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground hidden md:table-cell">
                Status
              </TableHead>
              <TableHead className="h-9 text-xs font-semibold text-muted-foreground text-right">
                Actions
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center">
                  No users found.
                </TableCell>
              </TableRow>
            ) : (
              users.map((user) => {
                // Permission Check:
                // Admins (who are not superusers) cannot modify Superusers.
                // Superusers can modify anyone.
                const isTargetSuperuser = user.is_superuser;
                const isCurrentSuperuser = currentUser?.is_superuser;
                const canModify = !isTargetSuperuser || isCurrentSuperuser;
                const displayName =
                  user.first_name || user.last_name
                    ? `${user.first_name || ""} ${user.last_name || ""}`.trim()
                    : null;

                return (
                  <TableRow key={user.id}>
                    <TableCell className="py-2 text-sm">
                      {displayName ? (
                        <span className="font-medium">{displayName}</span>
                      ) : (
                        <span className="text-muted-foreground italic text-xs">
                          Not set
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="py-2 text-sm font-medium">
                      {user.email}
                    </TableCell>
                    <TableCell className="py-2 hidden sm:table-cell">
                      <Badge
                        variant={user.is_superuser ? "outline" : "secondary"}
                        className={
                          user.is_superuser
                            ? "bg-purple-500/20 text-purple-400 border-purple-500/20 hover:bg-purple-500/30"
                            : ""
                        }
                      >
                        {user.is_superuser
                          ? "Superuser"
                          : user.role || "standard"}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-2 hidden md:table-cell">
                      <Badge
                        variant={user.is_active ? "default" : "outline"}
                        className={
                          user.is_active
                            ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/30"
                            : ""
                        }
                      >
                        {user.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-2 text-right space-x-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleEditRequest(user)}
                        disabled={!canModify}
                        title={
                          canModify ? "Edit User" : "Cannot modify Superuser"
                        }
                        className={!canModify ? "opacity-50" : ""}
                      >
                        <Pencil className="h-4 w-4 text-slate-400" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleResetRequest(user)}
                        disabled={!canModify}
                        title={
                          canModify
                            ? "Reset Password"
                            : "Cannot modify Superuser"
                        }
                        className={!canModify ? "opacity-50" : ""}
                      >
                        <Key className="h-4 w-4 text-blue-500" />
                      </Button>

                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() =>
                          toggleActiveMutation.mutate({
                            id: user.id,
                            isActive: !user.is_active,
                          })
                        }
                        disabled={toggleActiveMutation.isPending || !canModify}
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
                        onClick={() => handleDeleteRequest(user)}
                        disabled={deleteMutation.isPending || !canModify}
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
                );
              })
            )}
          </TableBody>
        </Table>
      </Card>

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
      />

      <Dialog
        open={resetState.open}
        onOpenChange={(open) =>
          setResetState((prev) => ({ ...prev, open: open }))
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>
              Set a new password for <b>{resetState.user?.email}</b>.
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(executeReset)}
              className="space-y-4"
            >
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>New Password</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="confirmPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Confirm Password</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="forcePasswordChange"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-4">
                    <FormControl>
                      <input
                        type="checkbox"
                        checked={field.value}
                        onChange={field.onChange}
                        className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel>Force Password Change</FormLabel>
                      <p className="text-sm text-muted-foreground">
                        User must change password on next login.
                      </p>
                    </div>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="disableMFA"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-4">
                    <FormControl>
                      <input
                        type="checkbox"
                        checked={field.value}
                        onChange={field.onChange}
                        className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel>Disable 2FA</FormLabel>
                      <p className="text-sm text-muted-foreground">
                        Remove 2FA protection for this user.
                      </p>
                    </div>
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setResetState({ open: false, user: null })}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={resetPasswordMutation.isPending}
                >
                  {resetPasswordMutation.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Reset Password
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      <EditUserDialog
        open={editState.open}
        onOpenChange={(open) =>
          setEditState((prev) => ({ ...prev, open: open }))
        }
        user={editState.user}
      />
    </>
  );
}
