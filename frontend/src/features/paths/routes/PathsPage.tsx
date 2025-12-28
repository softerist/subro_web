import { AddPathDialog } from "../components/AddPathDialog";
import { PathsTable } from "../components/PathsTable";

export function PathsPage() {
  return (
    <div className="space-y-6 page-enter page-stagger">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-blue-500 bg-clip-text text-transparent">
            Media Paths
          </h2>
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
