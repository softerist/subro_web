import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { CreateUserDialog } from "../components/CreateUserDialog";
import { UsersTable } from "../components/UsersTable";
import { adminApi } from "../api/admin";
import { useAuthStore } from "@/store/authStore";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function UsersPage() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((state) => state.user);
  const isSuperuser = currentUser?.is_superuser === true;

  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.getUsers,
  });

  const { data: openSignup, isLoading: isLoadingSignup } = useQuery({
    queryKey: ["open-signup"],
    queryFn: adminApi.getOpenSignup,
    enabled: isSuperuser,
  });

  const toggleSignupMutation = useMutation({
    mutationFn: adminApi.setOpenSignup,
    onSuccess: (newValue) => {
      queryClient.setQueryData(["open-signup"], newValue);
      toast.success(
        newValue
          ? "Open signup enabled - new users can now register"
          : "Open signup disabled - registration is now closed",
      );
    },
    onError: () => {
      toast.error("Failed to update open signup setting");
    },
  });

  return (
    <div className="space-y-6 px-4 pt-3 pb-3 page-enter page-stagger">
      <PageHeader
        title="User Management"
        description="Manage users, roles, and permissions."
        icon={Users}
        iconClassName="from-purple-500 to-pink-500 shadow-purple-500/20"
        action={<CreateUserDialog />}
      />

      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[11px] text-muted-foreground bg-accent/20 p-2.5 px-4 rounded-xl border border-border/40">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.5)]" />
            <span className="font-semibold text-purple-400/90 uppercase tracking-wider">
              Superuser:
            </span>
            <span className="opacity-80">
              Full system &quot;root&quot; access. Unrestricted permissions.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-slate-400" />
            <span className="font-semibold text-slate-300 uppercase tracking-wider">
              Admin:
            </span>
            <span className="opacity-80">
              Application management roles and access control.
            </span>
          </div>
        </div>

        {isSuperuser && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-2 bg-background/50 px-3 py-1.5 rounded-lg border border-border/60">
                  <UserPlus className="h-3.5 w-3.5 text-muted-foreground" />
                  <Label
                    htmlFor="open-signup"
                    className="text-xs font-medium cursor-pointer"
                  >
                    Open Signup
                  </Label>
                  <Switch
                    id="open-signup"
                    checked={openSignup ?? false}
                    onCheckedChange={(checked) =>
                      toggleSignupMutation.mutate(checked)
                    }
                    disabled={isLoadingSignup || toggleSignupMutation.isPending}
                    className="scale-75"
                  />
                </div>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Allow new users to register without admin approval</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      <UsersTable users={users || []} isLoading={isLoading} />
    </div>
  );
}
