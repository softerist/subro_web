import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  getSettings,
  updateSettings,
  SettingsUpdate,
  SettingsRead,
} from "@/lib/settingsApi";

type SettingsTab = "integrations" | "qbittorrent" | "paths";

export default function SettingsPage() {
  const [currentTab, setCurrentTab] = useState<SettingsTab>("integrations");
  const [settings, setSettings] = useState<SettingsRead | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form state for editable fields (need to re-enter to change)
  const [formData, setFormData] = useState<SettingsUpdate>({});

  // DeepL Key Management State
  const [deeplKeys, setDeeplKeys] = useState<string[]>([]);
  const [editingKeyIndex, setEditingKeyIndex] = useState<number | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getSettings();
      setSettings(data);
      // Initialize deeplKeys from existing settings
      if (data.deepl_api_keys && data.deepl_api_keys.length > 0) {
        setDeeplKeys(data.deepl_api_keys);
      }
    } catch (err) {
      setError("Failed to load settings");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      // Only send fields that have been modified
      const updatedSettings = await updateSettings(formData);
      setSettings(updatedSettings);
      setFormData({});
      setSuccess("Settings saved successfully!");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError("Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  const updateField = (
    key: keyof SettingsUpdate,
    value: string | number | string[],
  ) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const hasChanges = Object.keys(formData).length > 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-slate-400">
            Manage your application configuration
          </p>
        </div>
        {hasChanges && (
          <Button
            onClick={handleSave}
            disabled={isSaving}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {isSaving ? "Saving..." : "Save Changes"}
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert className="bg-green-900/50 border-green-700">
          <AlertDescription className="text-green-200">
            {success}
          </AlertDescription>
        </Alert>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-slate-700 pb-2">
        {[
          { id: "integrations", label: "API Integrations" },
          { id: "qbittorrent", label: "qBittorrent" },
          { id: "paths", label: "Media Paths" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setCurrentTab(tab.id as SettingsTab)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              currentTab === tab.id
                ? "bg-slate-700 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <Card className="bg-slate-800/50 border-slate-700">
        {/* API Integrations */}
        {currentTab === "integrations" && (
          <>
            <CardHeader>
              <CardTitle className="text-white">External Services</CardTitle>
              <CardDescription className="text-slate-400">
                Configure API keys for metadata providers and subtitle services.
                Masked values indicate configured credentials from env.prod
                file.
              </CardDescription>

              <div className="mt-4 ml-10 max-w-md border border-slate-700 rounded-md overflow-hidden bg-slate-900/40">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-800 text-slate-400 font-medium">
                    <tr>
                      <th className="px-3 py-2">Priority</th>
                      <th className="px-3 py-2">Source</th>
                      <th className="px-3 py-2">Example</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50 text-slate-300">
                    <tr>
                      <td className="px-3 py-2 text-cyan-400 font-bold">
                        1 (Highest)
                      </td>
                      <td className="px-3 py-2">Database</td>
                      <td className="px-3 py-2 text-slate-500">
                        Set via Settings UI
                      </td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 text-slate-400">2 (Fallback)</td>
                      <td className="px-3 py-2">Environment</td>
                      <td className="px-3 py-2 text-slate-500">
                        .env.prod file
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div className="px-3 py-2 text-[10px] text-slate-500 bg-slate-900/60 border-t border-slate-700/50">
                  If DB value is null/empty, system automatically uses
                  environment variable.
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-8">
              {/* Metadata Providers Section */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
                    <span className="text-white text-sm font-bold">📺</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">
                    Metadata Providers
                  </h3>
                </div>
                <div className="pl-10 space-y-4">
                  <div className="group relative max-w-md rounded-lg border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-600 transition-colors">
                    <div className="flex items-center gap-2 mb-2">
                      <Label className="text-xs uppercase tracking-wider text-slate-500 block">
                        TMDB API Key
                      </Label>
                      {settings?.tmdb_api_key && (
                        <span className="text-xs text-emerald-400">
                          ● Configured
                        </span>
                      )}
                    </div>
                    <Input
                      placeholder={settings?.tmdb_api_key || "Enter API key..."}
                      value={formData.tmdb_api_key || ""}
                      onChange={(e) =>
                        updateField("tmdb_api_key", e.target.value)
                      }
                      className="max-w-md bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-cyan-500"
                    />
                  </div>
                  <div className="group relative max-w-md rounded-lg border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-600 transition-colors">
                    <div className="flex items-center gap-2 mb-2">
                      <Label className="text-xs uppercase tracking-wider text-slate-500 block">
                        OMDB API Key
                      </Label>
                      {settings?.omdb_api_key && (
                        <span className="text-xs text-emerald-400">
                          ● Configured
                        </span>
                      )}
                    </div>
                    <Input
                      placeholder={settings?.omdb_api_key || "Enter API key..."}
                      value={formData.omdb_api_key || ""}
                      onChange={(e) =>
                        updateField("omdb_api_key", e.target.value)
                      }
                      className="max-w-md bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-cyan-500"
                    />
                  </div>
                </div>
              </div>

              {/* OpenSubtitles Section */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
                    <span className="text-white text-sm font-bold">💬</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">
                    OpenSubtitles
                  </h3>
                  {settings?.opensubtitles_api_key && (
                    <span className="ml-2 px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-xs rounded-full">
                      Connected
                    </span>
                  )}
                </div>
                <div className="pl-10 space-y-4">
                  <div className="max-w-md rounded-lg border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-600 transition-colors">
                    <Label className="text-xs uppercase tracking-wider text-slate-500 mb-2 block">
                      API Key
                    </Label>
                    <Input
                      placeholder={
                        settings?.opensubtitles_api_key || "Enter API key..."
                      }
                      value={formData.opensubtitles_api_key || ""}
                      onChange={(e) =>
                        updateField("opensubtitles_api_key", e.target.value)
                      }
                      className="max-w-md bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-amber-500"
                    />
                  </div>
                  <div className="max-w-md rounded-lg border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-600 transition-colors">
                    <Label className="text-xs uppercase tracking-wider text-slate-500 mb-2 block">
                      Username
                    </Label>
                    <Input
                      placeholder={
                        settings?.opensubtitles_username || "Enter username..."
                      }
                      value={formData.opensubtitles_username || ""}
                      onChange={(e) =>
                        updateField("opensubtitles_username", e.target.value)
                      }
                      className="max-w-md bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-amber-500"
                    />
                  </div>
                  <div className="max-w-md rounded-lg border border-slate-700 bg-slate-900/50 p-4 hover:border-slate-600 transition-colors">
                    <Label className="text-xs uppercase tracking-wider text-slate-500 mb-2 block">
                      Password
                    </Label>
                    <Input
                      type="password"
                      placeholder={
                        settings?.opensubtitles_password
                          ? "••••••••"
                          : "Enter password..."
                      }
                      value={formData.opensubtitles_password || ""}
                      onChange={(e) =>
                        updateField("opensubtitles_password", e.target.value)
                      }
                      className="max-w-md bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-amber-500"
                    />
                  </div>
                </div>
              </div>

              {/* DeepL Translation Section */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
                    <span className="text-white text-sm font-bold">🌐</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">
                    DeepL Translation
                  </h3>
                  {deeplKeys.length > 0 && (
                    <span className="ml-2 px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-xs rounded-full">
                      {deeplKeys.filter((k) => k.trim()).length} key
                      {deeplKeys.filter((k) => k.trim()).length !== 1
                        ? "s"
                        : ""}{" "}
                      configured
                    </span>
                  )}
                </div>
                <div className="pl-10 space-y-4 max-w-xl">
                  <p className="text-sm text-slate-500">
                    Manage DeepL API keys. Keys saved here will override
                    environment variable settings.
                  </p>

                  {/* Key Editor */}
                  <div className="space-y-3">
                    {deeplKeys.map((key, index) => {
                      const isEditing = editingKeyIndex === index;
                      const isMasked = key.includes("***");

                      return (
                        <div key={index} className="space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            {isEditing ? (
                              <Input
                                type="text"
                                placeholder="Enter DeepL API key..."
                                autoFocus
                                value={key}
                                onChange={(e) => {
                                  const newKeys = [...deeplKeys];
                                  newKeys[index] = e.target.value;
                                  setDeeplKeys(newKeys);
                                  setFormData((prev) => ({
                                    ...prev,
                                    deepl_api_keys: newKeys.filter((k) =>
                                      k.trim(),
                                    ),
                                  }));
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    e.preventDefault();
                                    setEditingKeyIndex(null);
                                    // Auto-save if there are changes
                                    if (Object.keys(formData).length > 0) {
                                      handleSave();
                                    }
                                  }
                                }}
                                className="flex-1 min-w-[200px] max-w-md bg-slate-800 border-slate-600 text-white placeholder:text-slate-500 focus:border-violet-500 font-mono text-sm"
                              />
                            ) : (
                              <div className="flex-1 min-w-[200px] max-w-md px-3 py-2 bg-slate-800 border border-slate-600 rounded-md font-mono text-sm text-slate-300">
                                {isMasked
                                  ? key
                                  : `${"•".repeat(Math.max(0, key.length - 4))}${key.slice(-4)}`}
                              </div>
                            )}

                            <div className="flex items-center gap-1">
                              {/* Edit Button */}
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={() =>
                                  setEditingKeyIndex(isEditing ? null : index)
                                }
                                title={isEditing ? "Done editing" : "Edit key"}
                              >
                                <Pencil className="h-4 w-4" />
                                <span className="sr-only">
                                  {isEditing ? "Done" : "Edit"}
                                </span>
                              </Button>

                              {/* Remove Button */}
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={() => {
                                  const newKeys = deeplKeys.filter(
                                    (_, i) => i !== index,
                                  );
                                  setDeeplKeys(newKeys);
                                  setFormData((prev) => ({
                                    ...prev,
                                    deepl_api_keys: newKeys.filter((k) =>
                                      k.trim(),
                                    ),
                                  }));
                                  setEditingKeyIndex(null);
                                }}
                                title="Remove key"
                              >
                                <Trash2 className="h-4 w-4 text-destructive" />
                                <span className="sr-only">Remove</span>
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        setDeeplKeys([...deeplKeys, ""]);
                        setEditingKeyIndex(deeplKeys.length);
                      }}
                      title="Add new key"
                    >
                      <Plus className="h-4 w-4" />
                      <span className="sr-only">Add Key</span>
                    </Button>
                  </div>

                  {/* Historical Usage Stats - merged with current UI state */}
                  {(() => {
                    // Compute merged usage stats: combine current deeplKeys with backend settings.deepl_usage
                    const mergedUsageStats: Array<{
                      key_alias: string;
                      character_count: number;
                      character_limit: number;
                      valid: boolean;
                    }> = [];

                    // Create a map of existing stats by suffix for quick lookup
                    const statsBySuffix = new Map<
                      string,
                      (typeof mergedUsageStats)[0]
                    >();
                    if (settings?.deepl_usage) {
                      settings.deepl_usage.forEach((usage) => {
                        const suffix = usage.key_alias.slice(-4);
                        statsBySuffix.set(suffix, usage);
                      });
                    }

                    // For each key in deeplKeys, find or create a usage stat
                    deeplKeys.forEach((key) => {
                      if (!key.trim()) return; // Skip empty keys

                      const suffix = key.slice(-4);
                      const existingStat = statsBySuffix.get(suffix);

                      if (existingStat) {
                        mergedUsageStats.push(existingStat);
                      } else {
                        // New unsaved key - show with 0/0
                        mergedUsageStats.push({
                          key_alias: `...${suffix}`,
                          character_count: 0,
                          character_limit: 0,
                          valid: true,
                        });
                      }
                    });

                    return mergedUsageStats.length > 0 ? (
                      <div className="mt-4 pt-4 border-t border-slate-700 max-w-md">
                        <h4 className="text-sm font-medium text-slate-400 mb-3">
                          Historical Usage (from translation logs)
                        </h4>
                        <div className="space-y-2">
                          {mergedUsageStats.map((usage, index) => {
                            const percent =
                              usage.character_limit > 0
                                ? Math.min(
                                    100,
                                    Math.round(
                                      (usage.character_count /
                                        usage.character_limit) *
                                        100,
                                    ),
                                  )
                                : 0;
                            const isFull = percent >= 100;
                            return (
                              <div
                                key={index}
                                className="bg-slate-900/50 rounded p-2 border border-slate-700"
                              >
                                <div className="flex justify-between items-center mb-1">
                                  <span className="text-xs font-mono text-slate-300">
                                    {usage.key_alias}
                                  </span>
                                  <div className="flex items-center gap-2">
                                    {usage.valid ? (
                                      <span className="text-[10px] text-emerald-400">
                                        Valid
                                      </span>
                                    ) : (
                                      <span className="text-[10px] text-red-400">
                                        Invalid
                                      </span>
                                    )}
                                    <span className="text-[10px] text-slate-500">
                                      {usage.character_count.toLocaleString()} /{" "}
                                      {usage.valid
                                        ? usage.character_limit.toLocaleString()
                                        : "0"}
                                    </span>
                                  </div>
                                </div>
                                <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                                  <div
                                    className={`h-full transition-all duration-500 ${isFull ? "bg-red-500" : "bg-blue-500"}`}
                                    style={{ width: `${percent}%` }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : null;
                  })()}
                </div>
              </div>
            </CardContent>
          </>
        )}

        {/* qBittorrent */}
        {currentTab === "qbittorrent" && (
          <>
            <CardHeader>
              <CardTitle className="text-white">qBittorrent Settings</CardTitle>
              <CardDescription className="text-slate-400">
                Configure connection to your qBittorrent instance for torrent
                monitoring.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-slate-300">Host</Label>
                  <Input
                    placeholder={settings?.qbittorrent_host || "Not configured"}
                    value={formData.qbittorrent_host || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_host", e.target.value)
                    }
                    className="bg-slate-900 border-slate-600 text-white placeholder:text-slate-500"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">Port</Label>
                  <Input
                    type="number"
                    placeholder={
                      settings?.qbittorrent_port?.toString() || "8080"
                    }
                    value={formData.qbittorrent_port || ""}
                    onChange={(e) =>
                      updateField(
                        "qbittorrent_port",
                        parseInt(e.target.value) || 0,
                      )
                    }
                    className="bg-slate-900 border-slate-600 text-white placeholder:text-slate-500"
                  />
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label className="text-slate-300">Username</Label>
                  <Input
                    placeholder={
                      settings?.qbittorrent_username || "Not configured"
                    }
                    value={formData.qbittorrent_username || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_username", e.target.value)
                    }
                    className="bg-slate-900 border-slate-600 text-white placeholder:text-slate-500"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-slate-300">Password</Label>
                  <Input
                    type="password"
                    placeholder={
                      settings?.qbittorrent_password
                        ? "••••••••"
                        : "Not configured"
                    }
                    value={formData.qbittorrent_password || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_password", e.target.value)
                    }
                    className="bg-slate-900 border-slate-600 text-white placeholder:text-slate-500"
                  />
                </div>
              </div>
            </CardContent>
          </>
        )}

        {/* Media Paths */}
        {currentTab === "paths" && (
          <>
            <CardHeader>
              <CardTitle className="text-white">
                Allowed Media Folders
              </CardTitle>
              <CardDescription className="text-slate-400">
                Specify which folders the application can access for subtitle
                downloads.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert className="bg-yellow-900/30 border-yellow-700">
                <AlertDescription className="text-yellow-200">
                  ⚠️ Ensure the server has read/write permissions for these
                  paths at the filesystem level.
                </AlertDescription>
              </Alert>
              <div className="space-y-2">
                <Label className="text-slate-300">Paths (one per line)</Label>
                <textarea
                  className="w-full h-32 bg-slate-900 border border-slate-600 rounded-md p-3 text-white placeholder:text-slate-500 font-mono text-sm"
                  placeholder={
                    settings?.allowed_media_folders?.join("\n") ||
                    "/mnt/media\n/data/videos"
                  }
                  value={(formData.allowed_media_folders || []).join("\n")}
                  onChange={(e) => {
                    const paths = e.target.value
                      .split("\n")
                      .filter((p) => p.trim());
                    updateField("allowed_media_folders", paths);
                  }}
                />
              </div>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
