import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldX } from "lucide-react";
import { toast } from "sonner";
import * as z from "zod";

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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { User } from "../types";
import { adminApi } from "../api/admin";

const editUserSchema = z
  .object({
    email: z.string().email("Please enter a valid email address"),
    role: z.enum(["admin", "standard"]),
    is_active: z.boolean(),
    is_verified: z.boolean(),
    force_password_change: z.boolean(),
    mfa_enabled: z.boolean(),
    // Password fields - optional, only used if setting new password
    new_password: z.string().optional(),
    confirm_password: z.string().optional(),
  })
  .refine(
    (data) => {
      // If new_password is set, confirm_password must match
      if (data.new_password && data.new_password.length > 0) {
        return data.new_password === data.confirm_password;
      }
      return true;
    },
    {
      message: "Passwords do not match",
      path: ["confirm_password"],
    },
  )
  .refine(
    (data) => {
      // If new_password is set, it must be at least 8 characters
      if (data.new_password && data.new_password.length > 0) {
        return data.new_password.length >= 8;
      }
      return true;
    },
    {
      message: "Password must be at least 8 characters",
      path: ["new_password"],
    },
  );

type EditUserFormValues = z.infer<typeof editUserSchema>;

interface EditUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User | null;
}

export function EditUserDialog({
  open,
  onOpenChange,
  user,
}: EditUserDialogProps) {
  const queryClient = useQueryClient();

  const form = useForm<EditUserFormValues>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      email: "",
      role: "standard",
      is_active: true,
      is_verified: false,
      force_password_change: false,
      mfa_enabled: false,
      new_password: "",
      confirm_password: "",
    },
  });

  // Reset form when user changes or dialog opens
  useEffect(() => {
    if (user && open) {
      form.reset({
        email: user.email,
        role: user.role,
        is_active: user.is_active,
        is_verified: user.is_verified,
        force_password_change: user.force_password_change ?? false,
        mfa_enabled: user.mfa_enabled ?? false,
        new_password: "",
        confirm_password: "",
      });
    }
  }, [user, open, form]);

  const updateMutation = useMutation({
    mutationFn: (data: EditUserFormValues) => {
      // Build update payload, only include password if set
      const payload: {
        email?: string;
        role?: "admin" | "standard";
        is_active?: boolean;
        is_verified?: boolean;
        force_password_change?: boolean;
        mfa_enabled?: boolean;
        password?: string;
      } = {
        email: data.email,
        role: data.role,
        is_active: data.is_active,
        is_verified: data.is_verified,
        force_password_change: data.force_password_change,
        mfa_enabled: data.mfa_enabled,
      };

      // Only include password if a new one was entered
      if (data.new_password && data.new_password.length > 0) {
        payload.password = data.new_password;
      }

      return adminApi.updateUser(user!.id, payload);
    },
    onSuccess: () => {
      toast.success("User updated successfully");
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(`Failed to update user: ${error.message}`);
    },
  });

  const onSubmit = (values: EditUserFormValues) => {
    updateMutation.mutate(values);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit User</DialogTitle>
          <DialogDescription>
            Update user details, permissions, and security settings.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            {/* Email Field */}
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email Address</FormLabel>
                  <FormControl>
                    <Input
                      type="email"
                      placeholder="user@example.com"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Role Field */}
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Role</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select a role" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="standard">Standard User</SelectItem>
                      <SelectItem value="admin">Administrator</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Administrators can manage users and application settings.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Account Status Section */}
            <div className="space-y-3 rounded-lg border p-4">
              <h4 className="text-sm font-medium leading-none mb-3">
                Account Status
              </h4>

              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel className="cursor-pointer">
                        Active Account
                      </FormLabel>
                      <FormDescription>
                        Inactive users cannot log in.
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="is_verified"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel className="cursor-pointer">
                        Email Verified
                      </FormLabel>
                      <FormDescription>
                        Mark the user&apos;s email as verified.
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />
            </div>

            {/* Password Section */}
            <div className="space-y-3 rounded-lg border p-4">
              <h4 className="text-sm font-medium leading-none mb-3">
                Password Settings
              </h4>

              <FormField
                control={form.control}
                name="new_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>New Password</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="Leave blank to keep current password"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="confirm_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Confirm Password</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="Confirm new password"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="force_password_change"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-start space-x-3 space-y-0 pt-2">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel className="cursor-pointer">
                        Force Password Change
                      </FormLabel>
                      <FormDescription>
                        User must change password on next login.
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />
            </div>

            {/* Security Section - MFA */}
            <div className="space-y-3 rounded-lg border p-4">
              <h4 className="text-sm font-medium leading-none mb-3">
                Security
              </h4>

              <FormField
                control={form.control}
                name="mfa_enabled"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <div className="flex items-center gap-2">
                        <FormLabel className="cursor-pointer">
                          Two-Factor Authentication (2FA)
                        </FormLabel>
                        {user?.mfa_enabled && (
                          <Badge
                            variant="outline"
                            className="text-xs bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                          >
                            Enabled
                          </Badge>
                        )}
                      </div>
                      <FormDescription>
                        {user?.mfa_enabled ? (
                          <span className="flex items-center gap-1 text-orange-400">
                            <ShieldX className="h-3 w-3" />
                            Unchecking will disable 2FA for this user.
                          </span>
                        ) : (
                          "User has not set up 2FA yet."
                        )}
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter className="gap-2 sm:gap-0">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
