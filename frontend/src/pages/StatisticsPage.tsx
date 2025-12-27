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

export default function StatisticsPage() {
  const [stats, setStats] = useState<TranslationStatsResponse | null>(null);
  const [history, setHistory] = useState<TranslationLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <div className="text-slate-400">Loading statistics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 page-enter">
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  const formatNumber = (n: number) => n.toLocaleString();

  return (
    <div className="space-y-6 page-enter page-stagger">
      <div>
        <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
          Translation Statistics
        </h1>
        <p className="text-slate-400">
          Overview of DeepL and Google Cloud translation usage
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* All Time */}
        <Card className="bg-slate-800/50 border-slate-700 soft-hover">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">
              All Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">
              {formatNumber(stats?.all_time.total_characters || 0)}
            </div>
            <p className="text-xs text-slate-500">
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
        <Card className="bg-slate-800/50 border-slate-700 soft-hover">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">
              Last 30 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">
              {formatNumber(stats?.last_30_days.total_characters || 0)}
            </div>
            <p className="text-xs text-slate-500">
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
        <Card className="bg-slate-800/50 border-slate-700 soft-hover">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-400">
              Last 7 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-white">
              {formatNumber(stats?.last_7_days.total_characters || 0)}
            </div>
            <p className="text-xs text-slate-500">
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
      <Card className="bg-slate-800/50 border-slate-700 soft-hover">
        <CardHeader>
          <CardTitle className="text-xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            Recent Translations
          </CardTitle>
          <CardDescription className="text-slate-400">
            Last 10 translation jobs
          </CardDescription>
        </CardHeader>
        <CardContent>
          {history.length === 0 ? (
            <p className="text-slate-500 text-center py-8">
              No translation history yet
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700">
                  <TableHead className="text-slate-400">File</TableHead>
                  <TableHead className="text-slate-400">Service</TableHead>
                  <TableHead className="text-slate-400">Characters</TableHead>
                  <TableHead className="text-slate-400">Status</TableHead>
                  <TableHead className="text-slate-400">Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((entry) => (
                  <TableRow key={entry.id} className="border-slate-700">
                    <TableCell className="text-white font-mono text-sm truncate max-w-[200px]">
                      {entry.file_name}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`px-2 py-0.5 text-xs rounded-full ${
                          entry.service_used.includes("deepl")
                            ? "bg-violet-500/20 text-violet-400"
                            : entry.service_used.includes("google")
                              ? "bg-blue-500/20 text-blue-400"
                              : "bg-slate-700 text-slate-400"
                        }`}
                      >
                        {entry.service_used}
                      </span>
                    </TableCell>
                    <TableCell className="text-slate-300">
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
                    <TableCell className="text-slate-400 text-sm">
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
