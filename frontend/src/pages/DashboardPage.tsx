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

  const handleSelectJob = (job: Job | null) => {
    setSelectedJobId(job ? job.id : null);
  };

  return (
    <div className="space-y-6 pb-8 xl:flex xl:flex-col xl:h-full xl:pb-0 xl:overflow-hidden page-enter page-stagger">
      {/* Dashboard Tiles Section */}
      <Card className="soft-hover">
        <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0 gap-2 flex-wrap sm:flex-nowrap">
          <CardTitle className="text-lg sm:text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent truncate flex-grow">
            Control Center
          </CardTitle>
          {isAdmin && (
            <div className="flex items-center space-x-2 shrink-0 ml-2">
              <Label
                htmlFor="edit-mode"
                className="text-sm font-medium text-muted-foreground"
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

      {/* Main content area - on xl, fills remaining viewport height */}
      <div className="flex flex-col xl:flex-row gap-6 xl:flex-1 xl:min-h-0">
        {/* Left Column: Form & List - scrolls independently on xl */}
        <div className="w-full xl:w-1/3 space-y-6 xl:overflow-y-auto xl:flex xl:flex-col">
          {/* New Job Form */}
          <Card className="soft-hover">
            <CardHeader>
              <CardTitle className="text-lg sm:text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                New Job
              </CardTitle>
              <CardDescription className="text-muted-foreground">
                Start a new subtitle download task.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <JobForm />
            </CardContent>
          </Card>

          {/* Job History - grows to fill remaining space */}
          <Card className="soft-hover xl:flex-1 xl:flex xl:flex-col xl:min-h-0 xl:overflow-hidden">
            <CardHeader>
              <CardTitle className="text-lg sm:text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                Job History
              </CardTitle>
            </CardHeader>
            <CardContent className="xl:flex-1 xl:overflow-y-auto">
              <JobHistoryList
                onSelectJob={handleSelectJob}
                selectedJobId={selectedJobId || undefined}
              />
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Log Viewer - fills height and scrolls internally on xl */}
        <div className="w-full xl:w-2/3 xl:flex xl:flex-col xl:min-h-0">
          <Card className="xl:flex-1 xl:flex xl:flex-col xl:min-h-0 xl:overflow-hidden soft-hover">
            <CardHeader className="py-4 shrink-0">
              <CardTitle className="text-lg sm:text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                Log Viewer
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 min-h-[300px] xl:flex-1 xl:min-h-0 xl:overflow-hidden">
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
