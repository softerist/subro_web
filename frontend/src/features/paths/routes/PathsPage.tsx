import { AddPathDialog } from "../components/AddPathDialog";
import { PathsTable } from "../components/PathsTable";

export function PathsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Storage Paths</h2>
          <p className="text-muted-foreground">
            Manage allowed directories for subtitle operations.
          </p>
        </div>
        <AddPathDialog />
      </div>

      <PathsTable />
    </div>
  );
}
