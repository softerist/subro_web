import { useState } from "react";
import { JobForm } from "@/features/jobs/components/JobForm";
import { JobHistoryList } from "@/features/jobs/components/JobHistoryList";
import { LogViewer } from "@/features/jobs/components/LogViewer";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Job } from "@/features/jobs/types";
import { TileGrid } from "@/features/dashboard/components/TileGrid";
import { useAuthStore } from "@/store/authStore";

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);

  const isAdmin = user?.role === "admin" || user?.is_superuser;

  const handleSelectJob = (job: Job) => {
    setSelectedJobId(job.id);
  };

  return (
    <div className="flex flex-col space-y-4 h-full">
      {/* Dashboard Tiles Section */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle>Launchpad</CardTitle>
          {isAdmin && (
            <div className="flex items-center space-x-2">
              <Label htmlFor="edit-mode" className="text-sm font-medium">
                Edit Layout
              </Label>
              <Switch
                id="edit-mode"
                checked={isEditMode}
                onCheckedChange={setIsEditMode}
              />
            </div>
          )}
        </CardHeader>
        <CardContent>
          <TileGrid isEditable={isEditMode} />
        </CardContent>
      </Card>

      <div className="flex flex-col lg:flex-row gap-4 h-full">
        {/* Left Column: Form & List */}
        <div className="w-full lg:w-1/3 flex flex-col gap-4">
          {/* New Job Form */}
          <Card>
            <CardHeader>
              <CardTitle>New Job</CardTitle>
              <CardDescription>
                Start a new subtitle download task.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <JobForm />
            </CardContent>
          </Card>

          {/* Job History */}
          <Card className="flex-1 flex flex-col min-h-[400px]">
            <CardHeader>
              <CardTitle>Job History</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 p-0 overflow-hidden">
              {/* We can wrap JobHistoryList in a scroll area if needed,
                         or JobHistoryList can handle its own scrolling.
                         Table component usually scrolls horizontally.
                     */}
              <div className="h-full overflow-auto p-4 pt-0">
                <JobHistoryList
                  onSelectJob={handleSelectJob}
                  selectedJobId={selectedJobId || undefined}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Log Viewer */}
        <div className="w-full lg:w-2/3 flex flex-col">
          <Card className="h-full flex flex-col">
            <CardHeader className="py-4">
              <CardTitle>Log Viewer</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 p-0">
              <LogViewer
                jobId={selectedJobId}
                className="h-full border-0 rounded-none"
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
