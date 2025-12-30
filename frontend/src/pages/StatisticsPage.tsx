import { useEffect, useState } from "react";
import { BarChart3, ChevronDown, ChevronUp } from "lucide-react";
import {
  getTranslationStats,
  TranslationStatsResponse,
  getTranslationHistory,
  TranslationLogEntry,
} from "@/lib/settingsApi";
import { PageHeader } from "@/components/common/PageHeader";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PathCell } from "@/components/ui/path-cell";
import { Button } from "@/components/ui/button";

export default function StatisticsPage() {
  const [stats, setStats] = useState<TranslationStatsResponse | null>(null);
  const [history, setHistory] = useState<TranslationLogEntry[]>([]);
  const [totalHistory, setTotalHistory] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [isFetchingMore, setIsFetchingMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedEntryId, setExpandedEntryId] = useState<number | null>(null);

  const PAGE_SIZE = 20;

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [statsData, historyData] = await Promise.all([
          getTranslationStats(),
          getTranslationHistory(1, PAGE_SIZE),
        ]);
        setStats(statsData);
        setHistory(historyData.items);
        setTotalHistory(historyData.total);
        setCurrentPage(1);
      } catch (err) {
        console.error("Failed to load statistics:", err);
        setError("Failed to load translation statistics");
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, []);

  const handleLoadMore = async () => {
    if (isFetchingMore || history.length >= totalHistory) return;

    setIsFetchingMore(true);
    try {
      const nextPage = currentPage + 1;
      const historyData = await getTranslationHistory(nextPage, PAGE_SIZE);
      setHistory((prev) => [...prev, ...historyData.items]);
      setCurrentPage(nextPage);
      setTotalHistory(historyData.total);
    } catch (err) {
      console.error("Failed to load more history:", err);
    } finally {
      setIsFetchingMore(false);
    }
  };

  const handleShowLess = () => {
    // Reset to first page without refetching if we want to be efficient,
    // or just slice the local array. Slicing local array is faster.
    setHistory((prev) => prev.slice(0, PAGE_SIZE));
    setCurrentPage(1);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 page-enter">
        <div className="text-muted-foreground">Loading statistics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 page-enter">
        <div className="text-destructive">{error}</div>
      </div>
    );
  }

  const formatNumber = (n: number) => n.toLocaleString();

  return (
    <div className="space-y-6 px-4 pt-3 pb-3 page-enter page-stagger">
      <PageHeader
        title="Translation Statistics"
        description="Overview of DeepL and Google Cloud translation usage"
        icon={BarChart3}
        iconClassName="from-sky-500 to-blue-600 shadow-blue-500/20"
      />

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* All Time */}
        <Card className="bg-card/50 border-border soft-hover">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              All Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-card-foreground">
              {formatNumber(stats?.all_time.total_characters || 0)}
            </div>
            <p className="text-xs text-muted-foreground">
              characters across{" "}
              {formatNumber(stats?.all_time.total_translations || 0)}{" "}
              translations
            </p>
            <div className="mt-2 flex gap-4 text-xs">
              <span className="text-violet-400">
                DeepL: {formatNumber(stats?.all_time.deepl_characters || 0)}
              </span>
              <span className="text-blue-400">
                Google: {formatNumber(stats?.all_time.google_characters || 0)}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Last 30 Days */}
        <Card className="bg-card/50 border-border soft-hover">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Last 30 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-card-foreground">
              {formatNumber(stats?.last_30_days.total_characters || 0)}
            </div>
            <p className="text-xs text-muted-foreground">
              characters across{" "}
              {formatNumber(stats?.last_30_days.total_translations || 0)}{" "}
              translations
            </p>
            <div className="mt-2 flex gap-4 text-xs">
              <span className="text-violet-400">
                DeepL: {formatNumber(stats?.last_30_days.deepl_characters || 0)}
              </span>
              <span className="text-blue-400">
                Google:{" "}
                {formatNumber(stats?.last_30_days.google_characters || 0)}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Last 7 Days */}
        <Card className="bg-card/50 border-border soft-hover">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Last 7 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-card-foreground">
              {formatNumber(stats?.last_7_days.total_characters || 0)}
            </div>
            <p className="text-xs text-muted-foreground">
              characters across{" "}
              {formatNumber(stats?.last_7_days.total_translations || 0)}{" "}
              translations
            </p>
            <div className="mt-2 flex gap-4 text-xs">
              <span className="text-violet-400">
                DeepL: {formatNumber(stats?.last_7_days.deepl_characters || 0)}
              </span>
              <span className="text-blue-400">
                Google:{" "}
                {formatNumber(stats?.last_7_days.google_characters || 0)}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Translations Table */}
      <Card className="bg-card/50 border-border soft-hover">
        <CardHeader>
          <CardTitle className="text-lg sm:text-xl font-bold title-gradient">
            Recent Translations
          </CardTitle>
          <CardDescription className="text-muted-foreground">
            Last 10 translation jobs
          </CardDescription>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              No translation history yet
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-b border-border/40">
                  <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground">
                    File
                  </TableHead>
                  <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground">
                    Service
                  </TableHead>
                  <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground">
                    Chars
                  </TableHead>
                  <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground">
                    Status
                  </TableHead>
                  <TableHead className="h-9 px-1 sm:px-4 text-[10px] sm:text-xs font-semibold text-muted-foreground">
                    Date
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((entry) => (
                  <TableRow
                    key={entry.id}
                    className="border-border cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() =>
                      setExpandedEntryId(
                        expandedEntryId === entry.id ? null : entry.id,
                      )
                    }
                  >
                    <TableCell className="py-2 px-1 sm:px-4">
                      <PathCell
                        path={entry.file_name}
                        className="text-foreground font-mono text-[10px] sm:text-sm"
                        defaultMaxWidth="max-w-[100px] sm:max-w-[200px] md:max-w-xl lg:max-w-3xl"
                        isExpanded={expandedEntryId === entry.id}
                        onToggle={() =>
                          setExpandedEntryId(
                            expandedEntryId === entry.id ? null : entry.id,
                          )
                        }
                      />
                    </TableCell>
                    <TableCell className="py-2 px-1 sm:px-4">
                      <span
                        className={`px-1.5 py-0.5 text-[10px] sm:text-xs rounded-full ${
                          entry.service_used.includes("deepl")
                            ? "bg-violet-500/20 text-violet-400"
                            : entry.service_used.includes("google")
                              ? "bg-blue-500/20 text-blue-400"
                              : "bg-muted/70 text-muted-foreground"
                        }`}
                      >
                        {entry.service_used}
                      </span>
                    </TableCell>
                    <TableCell className="py-2 px-1 sm:px-4 text-foreground text-[10px] sm:text-sm">
                      {formatNumber(entry.characters_billed)}
                    </TableCell>
                    <TableCell className="py-2 px-1 sm:px-4">
                      <span
                        className={`px-1.5 py-0.5 text-[10px] sm:text-xs rounded-full ${
                          entry.status === "success"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {entry.status}
                      </span>
                    </TableCell>
                    <TableCell className="py-2 px-1 sm:px-4 text-muted-foreground text-[10px] sm:text-sm">
                      {new Date(entry.timestamp).toLocaleDateString(undefined, {
                        month: "numeric",
                        day: "numeric",
                      })}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Show More/Less buttons */}
          {history.length > 0 && (
            <div className="flex flex-col items-center gap-3 mt-6">
              <div className="flex items-center justify-center gap-3">
                {currentPage > 1 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleShowLess}
                    className="h-8 text-xs gap-1.5"
                    disabled={isFetchingMore}
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                    Show Less
                  </Button>
                )}
                {history.length < totalHistory && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleLoadMore}
                    className="h-8 text-xs gap-1.5"
                    disabled={isFetchingMore}
                  >
                    {isFetchingMore ? (
                      <>
                        <span className="h-3 w-3 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                        Loading...
                      </>
                    ) : (
                      <>
                        <ChevronDown className="h-3.5 w-3.5" />
                        Show More ({totalHistory - history.length} remaining)
                      </>
                    )}
                  </Button>
                )}
              </div>
              {history.length >= totalHistory && totalHistory > PAGE_SIZE && (
                <p className="text-[10px] text-muted-foreground italic">
                  Showing all {totalHistory} records
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
