import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, RefreshCw, AlertCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { getAuditLogs, AuditLogFilters as Filters } from "../api/audit";
import { AuditLogTable } from "../components/AuditLogTable";
import { AuditLogFilters } from "../components/AuditLogFilters";
import { ExportAuditLogDialog } from "../components/ExportAuditLogDialog";
import { VerifyIntegrityDialog } from "../components/VerifyIntegrityDialog";

export default function AuditLogPage() {
  const [filters, setFilters] = useState<Filters>({
    page: 1,
    per_page: 25,
  });

  const { data, isLoading, isError, error, refetch, isPlaceholderData } =
    useQuery({
      queryKey: ["audit-logs", filters],
      queryFn: () => getAuditLogs(filters),
      placeholderData: (previousData) => previousData,
    });

  const handlePageChange = (newPage: number) => {
    setFilters((prev) => ({ ...prev, page: newPage }));
  };

  const handleFilterChange = (newFilters: Filters) => {
    setFilters({ ...newFilters, page: 1 }); // Reset to page 1 on filter change
  };

  const clearFilters = () => {
    setFilters({ page: 1, per_page: 25 });
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <ClipboardList className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Audit Logs</h1>
            <p className="text-muted-foreground text-sm">
              Track administrative actions and security events across the
              system.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <VerifyIntegrityDialog />
          <ExportAuditLogDialog filters={filters} />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw
              className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
            />
          </Button>
        </div>
      </div>

      <AuditLogFilters
        filters={filters}
        onFilterChange={handleFilterChange}
        onClear={clearFilters}
      />

      {isError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            Failed to load audit logs.{" "}
            {(error as Error)?.message || "Internal Server Error"}
          </AlertDescription>
        </Alert>
      )}

      <AuditLogTable
        logs={data?.items || []}
        isLoading={isLoading && !isPlaceholderData}
        total={data?.total || 0}
        page={filters.page || 1}
        perPage={filters.per_page || 25}
        onPageChange={handlePageChange}
      />
    </div>
  );
}
