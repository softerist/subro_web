import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Eye,
  Loader2,
  Trash2,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  StopCircle,
} from "lucide-react";
import { toast } from "sonner";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { jobsApi } from "../api/jobs";
import { JobStatusBadge } from "./JobStatusBadge";
import { Job } from "../types";
import { PathCell } from "@/components/ui/path-cell";

interface JobHistoryListProps {
  jobs?: Job[];
  onSelectJob: (job: Job | null) => void;
  selectedJobId?: string;
  visibleCount: number;
  initialCount: number;
  onLoadMore: () => void;
  onShowLess: () => void;
}

export function JobHistoryList({
  jobs,
  onSelectJob,
  selectedJobId,
  visibleCount,
  initialCount,
  onLoadMore,
  onShowLess,
}: JobHistoryListProps) {
  const [jobToDelete, setJobToDelete] = useState<Job | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const cancelMutation = useMutation({
    mutationFn: jobsApi.cancel,
    onError: (error: Error) => {
      toast.error(`Failed to delete job: ${error.message}`);
    },
  });

  const retryMutation = useMutation({
    mutationFn: jobsApi.retry,
    onSuccess: () => {
      toast.success("Job retry started");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to retry job: ${error.message}`);
    },
  });

  const stopMutation = useMutation({
    mutationFn: jobsApi.stop,
    onSuccess: () => {
      toast.success("Job cancellation requested");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error: Error) => {
      toast.error(`Failed to stop job: ${error.message}`);
    },
  });

  const handleDeleteClick = (e: React.MouseEvent, job: Job) => {
    e.stopPropagation();
    setJobToDelete(job);
  };

  const handleRetryClick = (e: React.MouseEvent, job: Job) => {
    e.stopPropagation();
    retryMutation.mutate(job.id);
  };

  const handleStopClick = (e: React.MouseEvent, job: Job) => {
    e.stopPropagation();
    stopMutation.mutate(job.id);
  };

  const confirmDelete = () => {
    if (jobToDelete) {
      cancelMutation.mutate(jobToDelete.id, {
        onSuccess: (_, deletedJobId) => {
          toast.success("Job deleted successfully");
          queryClient.invalidateQueries({ queryKey: ["jobs"] });
          if (selectedJobId === deletedJobId) {
            onSelectJob(null);
          }
          setJobToDelete(null);
        },
      });
    }
  };

  return (
    <>
      <div className="rounded-lg border border-border/60 overflow-hidden bg-card/50">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow className="hover:bg-transparent border-b border-border/40">
              <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground">
                Folder
              </TableHead>
              <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground w-24 sm:w-28 whitespace-nowrap">
                Status
              </TableHead>
              <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground w-20 sm:w-28 whitespace-nowrap">
                Created
              </TableHead>
              <TableHead className="text-right h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground w-16 sm:w-20 whitespace-nowrap">
                Actions
              </TableHead>
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
              jobs.slice(0, visibleCount).map((job) => (
                <TableRow
                  key={job.id}
                  className={`cursor-pointer transition-colors duration-200 ${selectedJobId === job.id ? "bg-primary/5 border-l-2 border-l-primary" : "hover:bg-muted/40"}`}
                  onClick={() => {
                    setExpandedJobId(expandedJobId === job.id ? null : job.id);
                    onSelectJob(job);
                  }}
                >
                  <TableCell className="py-2 px-1 sm:px-4 w-full">
                    <PathCell
                      path={job.folder_path}
                      className="text-[10px] sm:text-sm w-full"
                      defaultMaxWidth="max-w-full"
                      isExpanded={expandedJobId === job.id}
                      onToggle={() =>
                        setExpandedJobId(
                          expandedJobId === job.id ? null : job.id,
                        )
                      }
                    />
                  </TableCell>
                  <TableCell className="py-2 px-1 sm:px-4 w-24 sm:w-28 whitespace-nowrap">
                    <JobStatusBadge
                      status={job.status}
                      className="text-[10px] sm:text-xs px-1.5 py-0.5"
                    />
                  </TableCell>
                  <TableCell className="py-2 px-1 sm:px-4 text-[10px] sm:text-sm w-20 sm:w-28 whitespace-nowrap">
                    {format(new Date(job.submitted_at), "MM/dd HH:mm")}
                  </TableCell>
                  <TableCell className="py-2 px-1 sm:px-4 w-16 sm:w-20">
                    <div className="flex items-center justify-end gap-0.5 sm:gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 sm:h-8 sm:w-8"
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedJobId(
                            expandedJobId === job.id ? null : job.id,
                          );
                          onSelectJob(job);
                        }}
                        title="View Logs"
                      >
                        <Eye className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                        <span className="sr-only">View Logs</span>
                      </Button>
                      {/* Retry button - only for FAILED or CANCELLED jobs */}
                      {(job.status === "FAILED" ||
                        job.status === "CANCELLED") && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 sm:h-8 sm:w-8"
                          onClick={(e) => handleRetryClick(e, job)}
                          disabled={
                            retryMutation.isPending &&
                            retryMutation.variables === job.id
                          }
                          title="Retry Job"
                        >
                          {retryMutation.isPending &&
                          retryMutation.variables === job.id ? (
                            <Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-spin" />
                          ) : (
                            <RotateCcw className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-blue-500" />
                          )}
                          <span className="sr-only">Retry Job</span>
                        </Button>
                      )}
                      {/* Stop button - only for PENDING or RUNNING jobs */}
                      {(job.status === "PENDING" ||
                        job.status === "RUNNING") && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 sm:h-8 sm:w-8"
                          onClick={(e) => handleStopClick(e, job)}
                          disabled={
                            stopMutation.isPending &&
                            stopMutation.variables === job.id
                          }
                          title="Stop Job"
                        >
                          {stopMutation.isPending &&
                          stopMutation.variables === job.id ? (
                            <Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-spin" />
                          ) : (
                            <StopCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-orange-500" />
                          )}
                          <span className="sr-only">Stop Job</span>
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 sm:h-8 sm:w-8"
                        onClick={(e) => handleDeleteClick(e, job)}
                        disabled={
                          cancelMutation.isPending &&
                          cancelMutation.variables === job.id
                        }
                        title="Remove Job"
                      >
                        {cancelMutation.isPending &&
                        cancelMutation.variables === job.id ? (
                          <Loader2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-destructive" />
                        )}
                        <span className="sr-only">Remove Job</span>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Show More/Less buttons */}
      <div className="flex items-center justify-center gap-3 mt-4">
        {visibleCount > initialCount && (
          <Button
            variant="outline"
            size="sm"
            onClick={onShowLess}
            className="h-8 text-xs gap-1.5"
          >
            <ChevronUp className="h-3.5 w-3.5" />
            Show Less
          </Button>
        )}
        {jobs && jobs.length > visibleCount && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onLoadMore}
            className="h-8 text-xs gap-1.5"
          >
            <ChevronDown className="h-3.5 w-3.5" />
            Show More ({jobs.length - visibleCount})
          </Button>
        )}
      </div>

      <Dialog
        open={!!jobToDelete}
        onOpenChange={(open) => !open && setJobToDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Job</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this job? This action cannot be
              undone.
              {jobToDelete?.status === "RUNNING" &&
                " The job is currently running and will be stopped."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setJobToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                "Delete"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
