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
import { ScrollArea } from "@/components/ui/scroll-area";

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);

  const isAdmin = user?.role === "admin" || user?.is_superuser;

  const handleSelectJob = (job: Job) => {
    setSelectedJobId(job.id);
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Dashboard Tiles Section - Fixed height, shrinks to fit */}
      <Card className="shrink-0">
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

      {/* Main content area - fills remaining space */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0 mt-4">
        {/* Left Column: Form & List */}
        <div className="w-full lg:w-1/3 flex flex-col gap-4 min-h-0">
          {/* New Job Form - Fixed height */}
          <Card className="shrink-0">
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

          {/* Job History - Takes remaining space with scroll */}
          <Card className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <CardHeader className="shrink-0">
              <CardTitle>Job History</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 p-0 min-h-0 overflow-hidden">
              <ScrollArea className="h-full">
                <div className="p-4 pt-0">
                  <JobHistoryList
                    onSelectJob={handleSelectJob}
                    selectedJobId={selectedJobId || undefined}
                  />
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Log Viewer - Takes remaining space */}
        <div className="w-full lg:w-2/3 flex flex-col min-h-0">
          <Card className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <CardHeader className="py-4 shrink-0">
              <CardTitle>Log Viewer</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 p-0 min-h-0 overflow-hidden">
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
