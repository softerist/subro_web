import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, RefreshCw, AlertCircle } from "lucide-react";

import { PageHeader } from "@/components/common/PageHeader";
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
    per_page: 50, // Increased from 25 to 50
  });
  const [cursorByPage, setCursorByPage] = useState<
    Record<number, string | null>
  >({
    1: null,
  });

  const page = filters.page || 1;
  const cursor = useMemo(
    () => cursorByPage[page] ?? null,
    [cursorByPage, page],
  );

  const { data, isLoading, isError, error, refetch, isPlaceholderData } =
    useQuery({
      queryKey: ["audit-logs", { ...filters, cursor }],
      queryFn: () => getAuditLogs({ ...filters, cursor }),
      placeholderData: (previousData) => previousData,
    });

  useEffect(() => {
    if (!data?.next_cursor) return;
    setCursorByPage((prev) => ({
      ...prev,
      [page + 1]: data.next_cursor,
    }));
  }, [data?.next_cursor, page]);

  const handlePageChange = (newPage: number) => {
    if (newPage < 1) return;
    if (newPage > page && !cursorByPage[page + 1] && !data?.next_cursor) {
      return;
    }
    setFilters((prev) => ({ ...prev, page: newPage }));
  };

  const handleFilterChange = (newFilters: Filters) => {
    setCursorByPage({ 1: null });
    setFilters({ ...newFilters, page: 1 }); // Reset to page 1 on filter change
  };

  const clearFilters = () => {
    setCursorByPage({ 1: null });
    setFilters({ page: 1, per_page: 50 }); // Updated default
  };

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-4rem)] px-4 pt-3 pb-3 page-enter page-stagger">
      <PageHeader
        title="Audit Logs"
        description="Track administrative actions and security events across the system."
        icon={ClipboardList}
        iconClassName="from-sky-500 to-emerald-500 shadow-sky-500/20"
        action={
          <div className="flex items-center gap-2">
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
        }
      />

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

      <div className="flex-1 min-h-0 overflow-hidden">
        <AuditLogTable
          logs={data?.items || []}
          isLoading={isLoading && !isPlaceholderData}
          total={data?.total_count ?? 0}
          page={page}
          perPage={filters.per_page || 25}
          nextCursor={data?.next_cursor ?? null}
          onPageChange={handlePageChange}
        />
      </div>
    </div>
  );
}
