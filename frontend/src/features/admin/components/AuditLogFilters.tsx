import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AuditLogFilters as Filters } from "../api/audit";

interface AuditLogFiltersProps {
  filters: Filters;
  onFilterChange: (filters: Filters) => void;
  onClear: () => void;
}

export function AuditLogFilters({
  filters,
  onFilterChange,
  onClear,
}: AuditLogFiltersProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:flex-wrap gap-4 sm:items-end bg-card/50 p-4 rounded-lg border border-border/60">
      <div className="space-y-1.5 w-full sm:flex-1 sm:min-w-[200px]">
        <label
          htmlFor="actor-email-filter"
          className="text-xs font-semibold text-muted-foreground uppercase tracking-wider"
        >
          Actor Email
        </label>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            id="actor-email-filter"
            placeholder="Search by email..."
            className="pl-9 bg-background/50"
            value={filters.actor_email || ""}
            onChange={(e) =>
              onFilterChange({ ...filters, actor_email: e.target.value })
            }
          />
        </div>
      </div>

      <div className="space-y-1.5 w-full sm:w-48">
        <label
          htmlFor="severity-filter"
          className="text-xs font-semibold text-muted-foreground uppercase tracking-wider"
        >
          Severity
        </label>
        <Select
          value={filters.severity || "all"}
          onValueChange={(val) =>
            onFilterChange({
              ...filters,
              severity: val === "all" ? undefined : val,
            })
          }
        >
          <SelectTrigger id="severity-filter" className="bg-background/50">
            <SelectValue placeholder="All Severities" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Severities</SelectItem>
            <SelectItem value="info">Info</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="error">Error</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1.5 w-full sm:flex-1 sm:min-w-[200px]">
        <label
          htmlFor="action-filter"
          className="text-xs font-semibold text-muted-foreground uppercase tracking-wider"
        >
          Action
        </label>
        <Input
          id="action-filter"
          placeholder="e.g. auth.login"
          className="bg-background/50"
          value={filters.action || ""}
          onChange={(e) =>
            onFilterChange({ ...filters, action: e.target.value })
          }
        />
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={onClear}
        className="h-10 w-full sm:w-auto text-muted-foreground hover:text-foreground"
      >
        <X className="h-4 w-4 mr-2" />
        Clear
      </Button>
    </div>
  );
}
