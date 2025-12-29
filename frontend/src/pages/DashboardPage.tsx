import { useLayoutEffect, useRef, useState } from "react";
import { Responsive, WidthProvider } from "react-grid-layout/legacy";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const ResponsiveGridLayout = WidthProvider(Responsive);

interface GridItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minH?: number;
  minW?: number;
}

type GridPresets = Record<string, GridItem[]>;

import { JobForm } from "@/features/jobs/components/JobForm";
import { JobHistoryList } from "@/features/jobs/components/JobHistoryList";
import { LogViewer } from "@/features/jobs/components/LogViewer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Job } from "@/features/jobs/types";
import { TileGrid } from "@/features/dashboard/components/TileGrid";
import { StatCard } from "@/features/dashboard/components/StatCard";
import { useAuthStore } from "@/store/authStore";
import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "@/features/jobs/api/jobs";
import {
  Briefcase,
  Play,
  CheckCircle2,
  TrendingUp,
  GripHorizontal,
  RotateCcw,
} from "lucide-react";

const GRID_ROW_HEIGHT = 30;
const GRID_MARGIN_Y = 7;

// Default layouts for different breakpoints
const DEFAULT_LAYOUTS = {
  lg: [
    // Left column (4 cols): Quick Links on top (h=5 to fix scroll), New Job below (h=9). Total height = 14.
    { i: "quick-links", x: 0, y: 0, w: 4, h: 5, minH: 3 },
    { i: "new-job", x: 0, y: 5, w: 4, h: 9, minH: 6 },
    // Right column top (8 cols): Stats row (4 cards x 2 width = 8). Fixes "too long" tags.
    { i: "stat-total", x: 4, y: 0, w: 2, h: 2, minH: 2 },
    { i: "stat-active", x: 6, y: 0, w: 2, h: 2, minH: 2 },
    { i: "stat-today", x: 8, y: 0, w: 2, h: 2, minH: 2 },
    { i: "stat-success", x: 10, y: 0, w: 2, h: 2, minH: 2 },
    // Right column below stats: Recent Jobs. Starts at y=2. Ends at y=14. h = 12.
    { i: "recent-jobs", x: 4, y: 2, w: 8, h: 12, minH: 4 },
    // Bottom full width: Log Viewer. Starts at y=14. h=14 (Maximized with reduced top padding).
    { i: "logs", x: 0, y: 14, w: 12, h: 14, minH: 6 },
  ],
  md: [
    { i: "quick-links", x: 0, y: 0, w: 4, h: 5, minH: 3 },
    { i: "new-job", x: 0, y: 5, w: 4, h: 9, minH: 6 },
    { i: "stat-total", x: 4, y: 0, w: 2, h: 2 },
    { i: "stat-active", x: 6, y: 0, w: 2, h: 2 },
    { i: "stat-today", x: 8, y: 0, w: 2, h: 2 },
    { i: "stat-success", x: 10, y: 0, w: 1, h: 2 }, // Last one squeezes in md
    { i: "recent-jobs", x: 4, y: 2, w: 6, h: 12, minH: 4 },
    { i: "logs", x: 0, y: 14, w: 10, h: 14, minH: 6 },
  ],
  sm: [
    // Mobile layout: Quick Links first at top
    { i: "quick-links", x: 0, y: 0, w: 1, h: 5, minH: 3 },
    { i: "stat-total", x: 0, y: 5, w: 1, h: 2 },
    { i: "stat-active", x: 0, y: 7, w: 1, h: 2 },
    { i: "stat-today", x: 0, y: 9, w: 1, h: 2 },
    { i: "stat-success", x: 0, y: 11, w: 1, h: 2 },
    { i: "new-job", x: 0, y: 13, w: 1, h: 9, minH: 6 },
    { i: "recent-jobs", x: 0, y: 22, w: 1, h: 14, minH: 4 },
    { i: "logs", x: 0, y: 36, w: 1, h: 12, minH: 8 },
  ],
};

const STORAGE_KEY = "dashboard-layouts-v21";

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const isAdmin = user?.role === "admin" || user?.is_superuser; // Keep original isAdmin logic
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);
  const [activeBreakpoint, setActiveBreakpoint] = useState("lg");
  const [layouts, setLayouts] = useState<GridPresets>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : DEFAULT_LAYOUTS;
    } catch (e) {
      console.error("Failed to load layout from storage:", e);
      return DEFAULT_LAYOUTS;
    }
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleLayoutChange = (_currentLayout: any, allLayouts: any) => {
    setLayouts(allLayouts as GridPresets);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(allLayouts));
  };

  const handleResetLayout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setLayouts(DEFAULT_LAYOUTS);
    window.location.reload();
  };

  // Fetch job stats
  const { data: jobs } = useQuery({
    queryKey: ["jobs", { limit: 100 }],
    queryFn: () => jobsApi.getAll({ limit: 100 }),
    refetchInterval: 10000,
    enabled: !!accessToken,
  });

  // Calculate stats
  const totalJobs = jobs?.length || 0;
  const activeJobs = jobs?.filter((j) => j.status === "RUNNING").length || 0;
  const completedToday =
    jobs?.filter((j) => {
      const today = new Date();
      const jobDate = new Date(j.submitted_at);
      return (
        j.status === "SUCCEEDED" &&
        jobDate.toDateString() === today.toDateString()
      );
    }).length || 0;
  const successRate =
    totalJobs > 0
      ? Math.round(
          ((jobs?.filter((j) => j.status === "SUCCEEDED").length || 0) /
            totalJobs) *
            100,
        )
      : 0;

  const handleSelectJob = (job: Job | null) => {
    setSelectedJobId(job ? job.id : null);
  };

  // Pagination state for job list (no longer affects grid size)
  const INITIAL_VISIBLE = 5;
  const LOAD_MORE_INCREMENT = 10;
  const [visibleJobCount, setVisibleJobCount] = useState(INITIAL_VISIBLE);

  const handleLoadMore = () => {
    setVisibleJobCount((prev) => prev + LOAD_MORE_INCREMENT);
  };

  const handleShowLess = () => {
    setVisibleJobCount(INITIAL_VISIBLE);
  };

  const isMobileLayout = ["sm", "xs", "xxs"].includes(activeBreakpoint);

  const recentJobsContentRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const element = recentJobsContentRef.current;
    if (!element) {
      return;
    }

    let rafId: number | null = null;
    const updateGridHeight = () => {
      const rect = element.getBoundingClientRect();
      if (!rect.height) {
        return;
      }

      const nextH = Math.ceil(
        Math.max(0, rect.height - GRID_MARGIN_Y) /
          (GRID_ROW_HEIGHT + GRID_MARGIN_Y),
      );

      setLayouts((prev: GridPresets) => {
        const layoutKey = prev?.[activeBreakpoint]
          ? activeBreakpoint
          : prev?.sm
            ? "sm"
            : "lg";
        const currentLayout = prev?.[layoutKey];
        if (!currentLayout) {
          return prev;
        }

        const itemIndex = currentLayout.findIndex(
          (item: GridItem) => item.i === "recent-jobs",
        );
        if (itemIndex === -1) {
          return prev;
        }

        const currentItem = currentLayout[itemIndex];
        const minH = currentItem.minH ?? 1;
        const boundedH = Math.max(minH, nextH);
        if (currentItem.h === boundedH) {
          return prev;
        }

        const nextLayout = [...currentLayout];
        nextLayout[itemIndex] = { ...currentItem, h: boundedH };

        const nextLayouts = { ...prev, [layoutKey]: nextLayout };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(nextLayouts));
        return nextLayouts;
      });
    };

    const observer = new ResizeObserver(() => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame(updateGridHeight);
    });

    observer.observe(element);
    updateGridHeight();

    return () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      observer.disconnect();
    };
  }, [activeBreakpoint]);

  // Helper for drag handle
  const DragHandle = () => (
    <div className="drag-handle absolute top-0.5 right-0.5 p-1 cursor-grab active:cursor-grabbing text-muted-foreground/10 hover:text-muted-foreground/30 transition-colors z-20">
      <GripHorizontal className="h-3 w-3" />
    </div>
  );

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden px-3 pt-1 pb-1 relative">
      <ResponsiveGridLayout
        className="layout"
        layouts={layouts}
        breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
        cols={{ lg: 12, md: 10, sm: 1, xs: 1, xxs: 1 }}
        rowHeight={GRID_ROW_HEIGHT}
        measureBeforeMount
        draggableHandle=".drag-handle"
        onLayoutChange={handleLayoutChange}
        onBreakpointChange={(breakpoint) => setActiveBreakpoint(breakpoint)}
        margin={[GRID_MARGIN_Y, GRID_MARGIN_Y]}
        compactType="vertical"
        useCSSTransforms={!isMobileLayout}
      >
        {/* Individual Stat Cards */}
        <div key="stat-total" className="group">
          <StatCard
            icon={Briefcase}
            value={totalJobs}
            label="Total Jobs"
            variant="blue"
            className="h-full"
          />
          <DragHandle />
        </div>
        <div key="stat-active" className="group">
          <StatCard
            icon={Play}
            value={activeJobs}
            label="Active"
            variant="green"
            className="h-full"
          />
          <DragHandle />
        </div>
        <div key="stat-today" className="group">
          <StatCard
            icon={CheckCircle2}
            value={completedToday}
            label="Today"
            variant="purple"
            className="h-full"
          />
          <DragHandle />
        </div>
        <div key="stat-success" className="group">
          <StatCard
            icon={TrendingUp}
            value={`${successRate}%`}
            label="Success"
            variant="orange"
            className="h-full"
          />
          <DragHandle />
        </div>

        {/* Quick Links */}
        <Card key="quick-links" className="overflow-hidden flex flex-col">
          <CardHeader className="py-3 px-3 flex flex-row items-center justify-between space-y-0 relative shrink-0">
            <CardTitle className="text-[12px] font-semibold">
              Quick Links
            </CardTitle>
            <div className="flex items-center space-x-2 mr-5">
              {isAdmin && (
                <>
                  <Label
                    htmlFor="edit-mode"
                    className="text-[10px] text-muted-foreground"
                  >
                    Edit
                  </Label>
                  <Switch
                    id="edit-mode"
                    checked={isEditMode}
                    onCheckedChange={setIsEditMode}
                    className="scale-[0.6]"
                  />
                </>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={handleResetLayout}
                className="h-6 w-6 text-muted-foreground/60 hover:text-primary hover:bg-primary/5 transition-all duration-200"
                title="Reset to default layout"
                aria-label="Reset Layout"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            </div>
            <DragHandle />
          </CardHeader>
          <CardContent className="py-1 px-3 flex-1 overflow-auto flex items-center justify-center">
            <TileGrid isEditable={isEditMode} />
          </CardContent>
        </Card>

        {/* New Job */}
        <Card key="new-job" className="overflow-hidden flex flex-col">
          <CardHeader className="py-3 px-3 relative shrink-0">
            <CardTitle className="text-[12px] font-semibold flex items-center gap-1.5">
              <div className="h-5 w-5 rounded bg-gradient-to-br from-primary to-cyan-500 flex items-center justify-center">
                <Play className="h-2.5 w-2.5 text-white" />
              </div>
              New Job
            </CardTitle>
            <DragHandle />
          </CardHeader>
          <CardContent className="px-3 pt-1 pb-1 flex-1 overflow-auto">
            <JobForm />
          </CardContent>
        </Card>

        {/* Recent Jobs */}
        <Card key="recent-jobs" className="overflow-hidden">
          <div ref={recentJobsContentRef} className="flex flex-col">
            <CardHeader className="py-3 px-3 relative shrink-0">
              <CardTitle className="text-[12px] font-semibold flex items-center gap-1.5">
                <div className="h-5 w-5 rounded bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                  <Briefcase className="h-2.5 w-2.5 text-white" />
                </div>
                Recent Jobs
              </CardTitle>
              <DragHandle />
            </CardHeader>
            <CardContent className="px-3 pb-2">
              <JobHistoryList
                jobs={jobs}
                onSelectJob={handleSelectJob}
                selectedJobId={selectedJobId || undefined}
                visibleCount={visibleJobCount}
                initialCount={INITIAL_VISIBLE}
                onLoadMore={handleLoadMore}
                onShowLess={handleShowLess}
              />
            </CardContent>
          </div>
        </Card>

        {/* Log Viewer */}
        <Card key="logs" className="overflow-hidden flex flex-col">
          <CardHeader className="py-3 px-3 relative shrink-0">
            <CardTitle className="text-[12px] font-semibold flex items-center gap-1.5">
              <div className="h-5 w-5 rounded bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center">
                <CheckCircle2 className="h-2.5 w-2.5 text-white" />
              </div>
              Log Viewer
            </CardTitle>
            <DragHandle />
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-hidden relative">
            <LogViewer
              jobId={selectedJobId}
              className="h-full border-0 rounded-none absolute inset-0"
            />
          </CardContent>
        </Card>
      </ResponsiveGridLayout>
    </div>
  );
}
