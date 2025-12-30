import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { CreateUserDialog } from "../components/CreateUserDialog";
import { UsersTable } from "../components/UsersTable";
import { adminApi } from "../api/admin";

export function UsersPage() {
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.getUsers,
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

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-muted-foreground bg-accent/20 p-2.5 px-4 rounded-xl border border-border/40">
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

      <UsersTable users={users || []} isLoading={isLoading} />
    </div>
  );
}
