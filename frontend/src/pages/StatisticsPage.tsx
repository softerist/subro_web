import { useEffect, useState } from "react";
import {
  getTranslationStats,
  TranslationStatsResponse,
  getTranslationHistory,
  TranslationLogEntry,
} from "@/lib/settingsApi";
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

export default function StatisticsPage() {
  const [stats, setStats] = useState<TranslationStatsResponse | null>(null);
  const [history, setHistory] = useState<TranslationLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedEntryId, setExpandedEntryId] = useState<number | null>(null);

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [statsData, historyData] = await Promise.all([
          getTranslationStats(),
          getTranslationHistory(1, 10),
        ]);
        setStats(statsData);
        setHistory(historyData.items);
      } catch (err) {
        console.error("Failed to load statistics:", err);
        setError("Failed to load translation statistics");
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, []);

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
    <div className="space-y-6 page-enter page-stagger">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight title-gradient">
          Translation Statistics
        </h1>
        <p className="text-muted-foreground">
          Overview of DeepL and Google Cloud translation usage
        </p>
      </div>

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
                <TableRow className="border-border">
                  <TableHead className="text-muted-foreground">File</TableHead>
                  <TableHead className="text-muted-foreground">
                    Service
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    Characters
                  </TableHead>
                  <TableHead className="text-muted-foreground">
                    Status
                  </TableHead>
                  <TableHead className="text-muted-foreground">Date</TableHead>
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
                    <TableCell className="p-2">
                      <PathCell
                        path={entry.file_name}
                        className="text-foreground font-mono text-sm"
                        isExpanded={expandedEntryId === entry.id}
                        onToggle={() =>
                          setExpandedEntryId(
                            expandedEntryId === entry.id ? null : entry.id,
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <span
                        className={`px-2 py-0.5 text-xs rounded-full ${
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
                    <TableCell className="text-foreground">
                      {formatNumber(entry.characters_billed)}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`px-2 py-0.5 text-xs rounded-full ${
                          entry.status === "success"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-red-500/20 text-red-400"
                        }`}
                      >
                        {entry.status}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(entry.timestamp).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
