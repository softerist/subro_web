import { useState } from "react";
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

interface JobHistoryListProps {
  onSelectJob: (job: Job | null) => void;
  selectedJobId?: string;
}

export function JobHistoryList({
  onSelectJob,
  selectedJobId,
}: JobHistoryListProps) {
  const [jobToDelete, setJobToDelete] = useState<Job | null>(null);
  const queryClient = useQueryClient();
  const {
    data: jobs,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["jobs", { limit: 7 }],
    queryFn: () => jobsApi.getAll({ limit: 7 }),
    refetchInterval: 5000,
  });

  const cancelMutation = useMutation({
    mutationFn: jobsApi.cancel,
    onSuccess: (_, deletedJobId) => {
      toast.success("Job cancelled/deleted successfully");
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      if (selectedJobId === deletedJobId) {
        onSelectJob(null);
      }
      setJobToDelete(null);
    },
    onError: (error: Error) => {
      toast.error(`Failed to cancel job: ${error.message}`);
    },
  });

  const handleDeleteClick = (e: React.MouseEvent, job: Job) => {
    e.stopPropagation();
    setJobToDelete(job);
  };

  const confirmDelete = () => {
    if (jobToDelete) {
      cancelMutation.mutate(jobToDelete.id);
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
    <>
      <div className="rounded-md border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[200px] h-8">Target Folder</TableHead>
              <TableHead className="h-8">Status</TableHead>
              <TableHead className="h-8">Created At</TableHead>
              <TableHead className="text-right h-8">Actions</TableHead>
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
                  <TableCell
                    className="font-medium max-w-[200px] truncate py-2"
                    title={job.folder_path}
                  >
                    {job.folder_path}
                  </TableCell>
                  <TableCell className="py-2">
                    <JobStatusBadge status={job.status} />
                  </TableCell>
                  <TableCell className="py-2">
                    {format(new Date(job.submitted_at), "MMM d, HH:mm")}
                  </TableCell>
                  <TableCell className="text-right space-x-1 py-2">
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
                      onClick={(e) => handleDeleteClick(e, job)}
                      disabled={
                        cancelMutation.isPending &&
                        cancelMutation.variables === job.id
                      }
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
