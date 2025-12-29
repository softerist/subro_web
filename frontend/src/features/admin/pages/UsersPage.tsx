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

      <UsersTable users={users || []} isLoading={isLoading} />
    </div>
  );
}
