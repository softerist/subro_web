import { useQuery } from "@tanstack/react-query";
import { CreateUserDialog } from "../components/CreateUserDialog";
import { UsersTable } from "../components/UsersTable";
import { adminApi } from "../api/admin";

export function UsersPage() {
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: adminApi.getUsers,
  });

  return (
    <div className="space-y-6 page-enter page-stagger">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight title-gradient">
            User Management
          </h2>
          <p className="text-muted-foreground">
            Manage users, roles, and permissions.
          </p>
        </div>
        <CreateUserDialog />
      </div>

      <UsersTable users={users || []} isLoading={isLoading} />
    </div>
  );
}
