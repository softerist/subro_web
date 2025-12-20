import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Eye, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { jobsApi } from "../api/jobs";
import { JobStatusBadge } from "./JobStatusBadge";
import { Job } from "../types";

interface JobHistoryListProps {
  onSelectJob: (job: Job) => void;
  selectedJobId?: string;
}

export function JobHistoryList({
  onSelectJob,
  selectedJobId,
}: JobHistoryListProps) {
  const queryClient = useQueryClient();
  const {
    data: jobs,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["jobs"],
    queryFn: jobsApi.getAll,
    refetchInterval: 5000,
  });

  const cancelMutation = useMutation({
    mutationFn: jobsApi.cancel,
    onSuccess: () => {
      toast.success("Job cancelled/deleted successfully");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to cancel job: ${error.message}`);
    },
  });

  const handleCancelClick = (e: React.MouseEvent, jobId: string) => {
    e.stopPropagation();
    if (
      confirm(
        "Are you sure? This will stop the job (if running) and remove it immediately.",
      )
    ) {
      cancelMutation.mutate(jobId);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error) {
    return <div className="text-destructive">Failed to load jobs.</div>;
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Target Folder</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created At</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {!jobs || jobs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={4} className="h-24 text-center">
                No jobs found.
              </TableCell>
            </TableRow>
          ) : (
            jobs.map((job) => (
              <TableRow
                key={job.id}
                className={selectedJobId === job.id ? "bg-muted/50" : ""}
                onClick={() => onSelectJob(job)}
              >
                <TableCell className="font-medium">{job.folder_path}</TableCell>
                <TableCell>
                  <JobStatusBadge status={job.status} />
                </TableCell>
                <TableCell>
                  {format(new Date(job.submitted_at), "MMM d, HH:mm")}
                </TableCell>
                <TableCell className="text-right space-x-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectJob(job);
                    }}
                    title="View Logs"
                  >
                    <Eye className="h-4 w-4" />
                    <span className="sr-only">View Logs</span>
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => handleCancelClick(e, job.id)}
                    disabled={cancelMutation.isPending}
                    title="Remove Job"
                  >
                    {cancelMutation.isPending &&
                    cancelMutation.variables === job.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4 text-destructive" />
                    )}
                    <span className="sr-only">Remove Job</span>
                  </Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
