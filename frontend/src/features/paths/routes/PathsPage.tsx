import { Folder, Info } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { AddPathDialog } from "../components/AddPathDialog";
import { PathsTable } from "../components/PathsTable";
import { useAuthStore } from "@/store/authStore";

export function PathsPage() {
  const currentUser = useAuthStore((state) => state.user);
  return (
    <div className="space-y-6 px-4 pt-3 pb-3 page-enter page-stagger">
      <PageHeader
        title="Media Paths"
        description="Manage allowed directories for subtitle operations."
        icon={Folder}
        iconClassName="from-emerald-500 to-teal-500 shadow-emerald-500/20"
        action={<AddPathDialog />}
      />

      {!currentUser?.is_superuser && (
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4 text-sm text-blue-400">
          <p className="font-semibold flex items-center gap-2">
            <Info className="h-4 w-4" />
            Path Restrictions Active
          </p>
          <p className="mt-1 opacity-90 pl-6">
            As a standard user or admin, you can only add subdirectories of
            paths that have already been configured by a Superuser.
          </p>
        </div>
      )}

      <PathsTable />
    </div>
  );
}
