import { Folder } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { AddPathDialog } from "../components/AddPathDialog";
import { PathsTable } from "../components/PathsTable";

export function PathsPage() {
  return (
    <div className="space-y-6 px-4 pt-3 pb-3 page-enter page-stagger">
      <PageHeader
        title="Media Paths"
        description="Manage allowed directories for subtitle operations."
        icon={Folder}
        iconClassName="from-emerald-500 to-teal-500 shadow-emerald-500/20"
        action={<AddPathDialog />}
      />

      <PathsTable />
    </div>
  );
}
