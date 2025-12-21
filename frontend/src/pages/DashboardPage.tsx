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
    <div className="space-y-6 pb-8">
      {/* Dashboard Tiles Section */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
          <CardTitle>Launchpad</CardTitle>
          {isAdmin && (
            <div className="flex items-center space-x-2">
              <Label
                htmlFor="edit-mode"
                className="text-sm font-medium text-slate-400"
              >
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

      {/* Main content area */}
      <div className="flex flex-col xl:flex-row gap-6">
        {/* Left Column: Form & List */}
        <div className="w-full xl:w-1/3 space-y-6">
          {/* New Job Form */}
          <Card>
            <CardHeader>
              <CardTitle>New Job</CardTitle>
              <CardDescription className="text-slate-400">
                Start a new subtitle download task.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <JobForm />
            </CardContent>
          </Card>

          {/* Job History */}
          <Card className="flex flex-col overflow-hidden">
            <CardHeader>
              <CardTitle>Job History</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-hidden">
              <div className="max-h-[500px] lg:max-h-none overflow-y-auto overflow-x-hidden">
                <div className="p-4 pt-0">
                  <JobHistoryList
                    onSelectJob={handleSelectJob}
                    selectedJobId={selectedJobId || undefined}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Log Viewer */}
        <div className="w-full xl:w-2/3">
          <Card className="h-full flex flex-col overflow-hidden">
            <CardHeader className="py-4 shrink-0">
              <CardTitle>Log Viewer</CardTitle>
            </CardHeader>
            <CardContent
              className={`flex-1 p-0 overflow-hidden ${selectedJobId ? "min-h-[400px]" : "min-h-[100px]"} lg:min-h-0`}
            >
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
