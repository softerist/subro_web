import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useNavigate } from "react-router-dom";
import { Loader2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { useMutation } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/apiClient";
import { useAuthStore } from "@/store/authStore";

const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Current password is required"),
    new_password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .regex(/[A-Z]/, "Must contain at least one uppercase letter")
      .regex(/[a-z]/, "Must contain at least one lowercase letter")
      .regex(/[0-9]/, "Must contain at least one number"),
    confirm_password: z.string(),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>;

export function ForceChangePasswordPage() {
  const navigate = useNavigate();
  const { user, setUser } = useAuthStore();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const form = useForm<ChangePasswordFormValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
  });

  const changePasswordMutation = useMutation({
    mutationFn: async (data: ChangePasswordFormValues) => {
      // Assuming existing endpoint: PATCH /auth/password
      // Body: { current_password: "...", new_password: "..." }
      await api.patch("/v1/auth/password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });
    },
    onSuccess: () => {
      toast.success("Password changed successfully!");
      // Update local user state to remove the flag so redirect doesn't trigger again
      if (user) {
        setUser({ ...user, force_password_change: false });
      }
      navigate("/");
    },
    onError: (error: unknown) => {
      console.error(error);
      const errorResponse = error as {
        response?: { data?: { detail?: string } };
      };
      const detail =
        errorResponse?.response?.data?.detail || "Failed to change password";
      toast.error(detail);
    },
  });

  const onSubmit = (data: ChangePasswordFormValues) => {
    setIsSubmitting(true);
    changePasswordMutation.mutate(data, {
      onSettled: () => setIsSubmitting(false),
    });
  };

  return (
    <div className="container flex h-screen w-screen flex-col items-center justify-center">
      <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
        <div className="flex flex-col space-y-2 text-center">
          <div className="mx-auto h-12 w-12 rounded-full bg-red-100 p-3">
            <ShieldAlert className="h-6 w-6 text-red-600" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Update Password
          </h1>
          <p className="text-sm text-muted-foreground">
            Your password was reset by an administrator. You must set a new
            password to continue.
          </p>
        </div>

        <div className="grid gap-6">
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="current_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Temporary Password</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="The one you just used"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="new_password"
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
                name="confirm_password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Confirm New Password</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" className="w-full" disabled={isSubmitting}>
                {isSubmitting && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Change Password
              </Button>
            </form>
          </Form>
        </div>
      </div>
    </div>
  );
}
