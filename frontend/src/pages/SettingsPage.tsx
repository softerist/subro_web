import { useEffect, useState, useRef } from "react";
import { Plus, Trash2, AlertCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
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
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { SavePill } from "@/components/common/SavePill";

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

  // Confirmation Dialog State
  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    type: "deepl" | "google" | null;
    index?: number;
    title: string;
    description: React.ReactNode;
    targetRect?: { top: number; left: number; width: number; height: number };
  }>({
    open: false,
    type: null,
    title: "",
    description: null,
  });

  // Ref for dynamic SavePill centering
  const cardRef = useRef<HTMLDivElement>(null);

  const hasChanges = Object.keys(formData).length > 0;

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async (silent = false) => {
    if (!silent) setIsLoading(true);
    setError(null);
    try {
      const data = await getSettings();
      setSettings(data);
      // Initialize deeplKeys from existing settings
      if (data.deepl_api_keys && data.deepl_api_keys.length > 0) {
        // Only update input fields if we are NOT editing them right now?
        // Actually, better to only sync if list length changes or on first load,
        // to avoid overwriting user typing.
        // But here we just set it initially.
        setDeeplKeys(data.deepl_api_keys);
      }
    } catch (err) {
      setError("Failed to load settings");
    } finally {
      if (!silent) setIsLoading(false);
    }
  };

  // Poll for updates if any key is validating
  useEffect(() => {
    if (!settings?.deepl_usage) return;

    // Check if any key is strictly "Not Validated" (valid === null)
    // In our API response, valid is null if pending.
    const hasPending = settings.deepl_usage.some((u) => u.valid === null);

    if (hasPending) {
      const interval = setInterval(() => {
        loadSettings(true);
      }, 1000); // Poll every 1 second
      return () => clearInterval(interval);
    }
  }, [settings?.deepl_usage]);

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      // Only send fields that have been modified
      const updatedSettings = await updateSettings(formData);
      setSettings(updatedSettings);

      // Sync DeepL keys state to ensure they are masked immediately
      if (updatedSettings.deepl_api_keys) {
        setDeeplKeys(updatedSettings.deepl_api_keys);
      }

      setFormData({});
      setSuccess("Settings saved successfully!");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError("Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSave();
    }
  };

  const updateField = (
    key: keyof SettingsUpdate,
    value: string | number | string[],
  ) => {
    setFormData((prev) => {
      const newData = { ...prev, [key]: value };

      // Check if value matches original setting to avoid dirty state if changed back
      if (settings) {
        const originalValue = (settings as unknown as Record<string, unknown>)[
          key
        ];
        let isEqual = false;

        // Array comparison (for allowed_media_folders)
        if (Array.isArray(value) && Array.isArray(originalValue)) {
          isEqual = JSON.stringify(value) === JSON.stringify(originalValue);
        }
        // Strict equality for primitives
        else if (value === originalValue) {
          isEqual = true;
        }
        // Handle empty string vs null/undefined mismatch
        else if ((value === "" || value === null) && !originalValue) {
          // Special case: If credentials are configured but hidden (undefined in settings),
          // setting them to "" is a valid change (Removal).
          if (
            key === "google_cloud_credentials" &&
            (settings as unknown as Record<string, unknown>)
              .google_cloud_configured
          ) {
            isEqual = false;
          } else {
            isEqual = true;
          }
        }

        if (isEqual) {
          const { [key]: _, ...rest } = newData;
          return rest;
        }
      }
      return newData;
    });
  };

  const handleKeyDeleteRequest = (index: number, event: React.MouseEvent) => {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    setConfirmState({
      open: true,
      type: "deepl",
      index,
      title: "Remove API Key?",
      description: "Are you sure you want to remove this DeepL API key?",
      targetRect: {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      },
    });
  };

  const handleGoogleRemoveRequest = (event: React.MouseEvent) => {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    setConfirmState({
      open: true,
      type: "google",
      title: "Remove Google Cloud Configuration?",
      description:
        "Are you sure you want to remove the Google Cloud credentials?",
      targetRect: {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      },
    });
  };

  const executeDelete = async () => {
    setIsSaving(true);
    setConfirmState((prev) => ({ ...prev, open: false })); // Close dialog immediately or wait? Better wait? No, user wants feedback.
    // Actually confirming acts as "Save".
    // We can keep dialog open if we wanted loading state there.
    // ConfirmDialog has isLoading prop.
    // Let's implement isLoading on Dialog.

    try {
      let updatePayload: Partial<SettingsUpdate> = {};
      let successMsg = "";

      if (confirmState.type === "deepl" && confirmState.index !== undefined) {
        // DeepL Deletion
        const newKeys = deeplKeys.filter((_, i) => i !== confirmState.index);
        updatePayload = { deepl_api_keys: newKeys };
        successMsg = "DeepL key removed successfully.";
      } else if (confirmState.type === "google") {
        // Google Cloud Removal
        updatePayload = { google_cloud_credentials: "" };
        successMsg = "Google Cloud configuration removed.";
      }

      if (Object.keys(updatePayload).length > 0) {
        const updatedSettings = await updateSettings(updatePayload);
        setSettings(updatedSettings);

        // Update local state
        if (updatedSettings.deepl_api_keys) {
          setDeeplKeys(updatedSettings.deepl_api_keys);
        }

        // Clean up formData if it contained related pending changes
        setFormData((prev) => {
          const newData = { ...prev };
          if (confirmState.type === "deepl") {
            delete newData.deepl_api_keys;
          } else if (confirmState.type === "google") {
            delete newData.google_cloud_credentials;
          }
          return newData;
        });

        setSuccess(successMsg);
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (err) {
      setError("Failed to execute removal.");
    } finally {
      setIsSaving(false);
      setConfirmState((prev) => ({ ...prev, open: false, type: null }));
    }
  };

  const handleDiscard = () => {
    setFormData({});
    if (settings?.deepl_api_keys) {
      setDeeplKeys(settings.deepl_api_keys);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 page-enter">
        <div className="text-slate-400">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 page-enter page-stagger">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-slate-400">
            Manage your application configuration
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
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
      <Card
        ref={cardRef}
        className="bg-slate-800/50 border-slate-700 soft-hover"
      >
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

              <p className="mt-2 text-xs text-slate-500 italic">
                💡 Settings saved here override environment variables
                (.env.prod).
              </p>
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
                <div className="pl-10 space-y-6 max-w-xl">
                  {/* TMDB API Key */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs uppercase tracking-wider text-slate-500">
                        TMDB API Key
                      </Label>
                      {settings?.tmdb_api_key &&
                      settings.tmdb_api_key.trim() !== "" ? (
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            settings?.tmdb_valid === true
                              ? "bg-emerald-500/20 text-emerald-400"
                              : settings?.tmdb_valid === false
                                ? "bg-red-500/20 text-red-400"
                                : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {settings?.tmdb_valid === true
                            ? "Valid"
                            : settings?.tmdb_valid === false
                              ? "Invalid"
                              : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400">
                          Not Connected
                        </span>
                      )}
                    </div>
                    <Input
                      placeholder={settings?.tmdb_api_key || "Enter API key..."}
                      value={formData.tmdb_api_key || ""}
                      onChange={(e) =>
                        updateField("tmdb_api_key", e.target.value)
                      }
                      onKeyDown={handleInputKeyDown}
                      className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 h-10 w-full"
                    />
                  </div>

                  {/* OMDB API Key */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs uppercase tracking-wider text-slate-500">
                        OMDB API Key
                      </Label>
                      {settings?.omdb_api_key &&
                      settings.omdb_api_key.trim() !== "" ? (
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            settings?.omdb_valid === true
                              ? "bg-emerald-500/20 text-emerald-400"
                              : settings?.omdb_valid === false
                                ? "bg-red-500/20 text-red-400"
                                : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {settings?.omdb_valid === true
                            ? "Valid"
                            : settings?.omdb_valid === false
                              ? "Invalid"
                              : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400">
                          Not Connected
                        </span>
                      )}
                    </div>
                    <Input
                      placeholder={settings?.omdb_api_key || "Enter API key..."}
                      value={formData.omdb_api_key || ""}
                      onChange={(e) =>
                        updateField("omdb_api_key", e.target.value)
                      }
                      onKeyDown={handleInputKeyDown}
                      className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-cyan-500 h-10 w-full"
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
                </div>
                <div className="pl-10 space-y-6 max-w-xl">
                  {/* API Key */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs uppercase tracking-wider text-slate-500">
                        API Key
                      </Label>
                      {settings?.opensubtitles_api_key &&
                      settings.opensubtitles_api_key.trim() !== "" ? (
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            settings?.opensubtitles_key_valid === true
                              ? "bg-emerald-500/20 text-emerald-400"
                              : settings?.opensubtitles_key_valid === false
                                ? "bg-red-500/20 text-red-400"
                                : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {settings?.opensubtitles_key_valid === true
                            ? "Valid"
                            : settings?.opensubtitles_key_valid === false
                              ? "Invalid"
                              : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400">
                          Not Connected
                        </span>
                      )}
                    </div>
                    <Input
                      placeholder={
                        settings?.opensubtitles_api_key || "Enter API key..."
                      }
                      value={formData.opensubtitles_api_key || ""}
                      onChange={(e) =>
                        updateField("opensubtitles_api_key", e.target.value)
                      }
                      onKeyDown={handleInputKeyDown}
                      className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-amber-500 h-10 w-full"
                    />
                  </div>

                  {/* OpenSubtitles Credentials */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs uppercase tracking-wider text-slate-500">
                        Credentials
                      </Label>
                      {(settings?.opensubtitles_username &&
                        settings.opensubtitles_username.trim() !== "") ||
                      (settings?.opensubtitles_password &&
                        settings.opensubtitles_password.trim() !== "") ? (
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            settings?.opensubtitles_valid === true
                              ? "bg-emerald-500/20 text-emerald-400"
                              : settings?.opensubtitles_valid === false
                                ? "bg-red-500/20 text-red-400"
                                : "bg-yellow-500/20 text-yellow-400"
                          }`}
                        >
                          {settings?.opensubtitles_valid === true
                            ? "Valid"
                            : !settings?.opensubtitles_username
                              ? "Username Required"
                              : !settings?.opensubtitles_password
                                ? "Password Required"
                                : settings?.opensubtitles_valid === false
                                  ? "Invalid Credentials"
                                  : settings?.opensubtitles_key_valid === false
                                    ? "Valid API Key required"
                                    : !settings?.opensubtitles_api_key
                                      ? "API Key Invalid"
                                      : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400">
                          Not Connected
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-[10px] uppercase tracking-widest text-slate-500">
                          Username
                        </Label>
                        <Input
                          placeholder={
                            settings?.opensubtitles_username ||
                            "Enter username..."
                          }
                          autoComplete="off"
                          value={formData.opensubtitles_username || ""}
                          onChange={(e) =>
                            updateField(
                              "opensubtitles_username",
                              e.target.value,
                            )
                          }
                          onKeyDown={handleInputKeyDown}
                          className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-amber-500 h-10 w-full"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label className="text-[10px] uppercase tracking-widest text-slate-500">
                          Password
                        </Label>
                        <Input
                          type="password"
                          autoComplete="new-password"
                          placeholder={
                            settings?.opensubtitles_password
                              ? "••••••••"
                              : "Enter password..."
                          }
                          value={formData.opensubtitles_password || ""}
                          onChange={(e) =>
                            updateField(
                              "opensubtitles_password",
                              e.target.value,
                            )
                          }
                          onKeyDown={handleInputKeyDown}
                          className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-amber-500 h-10 w-full"
                        />
                      </div>
                    </div>
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
                <div className="pl-10 space-y-6 max-w-xl">
                  <div className="space-y-4">
                    <p className="text-sm text-slate-500">
                      Manage DeepL API keys. Keys saved here will override
                      environment variable settings.
                    </p>
                  </div>

                  {/* Key Editor */}
                  <div className="space-y-6">
                    <AnimatePresence mode="popLayout">
                      {deeplKeys.map((key, index) => {
                        const isEditing = editingKeyIndex === index;
                        const isMasked = key.includes("***");

                        // Find validation status and usage for this key
                        let status:
                          | "valid"
                          | "invalid"
                          | "not_validated"
                          | "not_connected" = "not_validated";
                        let usage = undefined;

                        if (!key.trim()) {
                          status = "not_connected";
                        } else {
                          let suffix = key;
                          if (key.length >= 8) {
                            suffix = key.slice(-8);
                          } else if (key.includes("...")) {
                            suffix = key.replace(/^\.\.\./, "");
                          }

                          usage = settings?.deepl_usage?.find((u) =>
                            u.key_alias.endsWith(suffix),
                          );
                          if (usage) {
                            status =
                              usage.valid === true
                                ? "valid"
                                : usage.valid === false
                                  ? "invalid"
                                  : "not_validated";
                          }
                        }

                        return (
                          <motion.div
                            key={index}
                            layout
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95 }}
                            transition={{ duration: 0.2 }}
                            className="space-y-3 p-4 bg-slate-900/30 rounded-xl border border-slate-700/50 transition-all duration-300 hover:border-slate-600 hover:bg-slate-900/40"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <Label className="text-xs uppercase tracking-wider text-slate-500">
                                Key {index + 1}
                              </Label>
                              {status === "valid" ? (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400">
                                  Valid
                                </span>
                              ) : status === "invalid" ? (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-red-500/20 text-red-400">
                                  Invalid
                                </span>
                              ) : status === "not_connected" ? (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400">
                                  Not Connected
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-yellow-500/20 text-yellow-400">
                                  Not Validated
                                </span>
                              )}
                            </div>

                            <div className="relative group">
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
                                    const updatedKeys = newKeys.filter((k) =>
                                      k.trim(),
                                    );

                                    // Check if keys match original settings
                                    let isEqual = false;
                                    if (settings?.deepl_api_keys) {
                                      isEqual =
                                        JSON.stringify(updatedKeys) ===
                                        JSON.stringify(settings.deepl_api_keys);
                                    } else if (updatedKeys.length === 0) {
                                      isEqual = true;
                                    }

                                    setFormData((prev) => {
                                      if (isEqual) {
                                        const { deepl_api_keys: _, ...rest } =
                                          prev;
                                        return rest;
                                      }
                                      return {
                                        ...prev,
                                        deepl_api_keys: updatedKeys,
                                      };
                                    });
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
                                  className="w-full pr-10 bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 focus:border-violet-500 font-mono text-sm h-10 transition-all duration-300"
                                />
                              ) : (
                                <div
                                  className="w-full pr-10 px-3 py-2 bg-slate-900/50 border border-slate-700 rounded-md font-mono text-sm text-slate-300 overflow-hidden text-ellipsis whitespace-nowrap cursor-pointer hover:border-violet-500 hover:bg-slate-800 transition-colors"
                                  onClick={() => setEditingKeyIndex(index)}
                                  title="Click to edit"
                                >
                                  {isMasked
                                    ? key
                                    : `${"•".repeat(Math.max(0, key.length - 8))}${key.slice(-8)}`}
                                </div>
                              )}

                              {/* Remove Button - Inside Field */}
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={(e) =>
                                  handleKeyDeleteRequest(index, e)
                                }
                                className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-slate-500 hover:text-destructive hover:bg-transparent"
                                title="Remove key"
                              >
                                <Trash2 className="h-4 w-4" />
                                <span className="sr-only">Remove</span>
                              </Button>
                            </div>

                            {/* Usage Progress Bar - Integrated inside */}
                            {usage && (
                              <div className="mt-2 space-y-1">
                                <div className="flex justify-between items-center text-[10px] text-slate-500">
                                  <span>Character Usage</span>
                                  <span>
                                    {usage.character_count.toLocaleString()} /{" "}
                                    {usage.valid
                                      ? usage.character_limit.toLocaleString()
                                      : "0"}
                                  </span>
                                </div>
                                {(() => {
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
                                    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                                      <div
                                        className={`h-full transition-all duration-500 ${isFull ? "bg-red-500" : "bg-violet-500"}`}
                                        style={{ width: `${percent}%` }}
                                      />
                                    </div>
                                  );
                                })()}
                              </div>
                            )}
                          </motion.div>
                        );
                      })}
                    </AnimatePresence>

                    <button
                      type="button"
                      onClick={() => {
                        setDeeplKeys([...deeplKeys, ""]);
                        setEditingKeyIndex(deeplKeys.length);
                        // Don't mark as having changes yet - wait for user to type something
                      }}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 rounded-lg text-white text-sm font-medium transition-all shadow-lg shadow-violet-500/20 hover:shadow-violet-500/40"
                    >
                      <Plus className="h-4 w-4" />
                      Add API Key
                    </button>
                  </div>
                </div>
              </div>

              {/* Google Cloud Translation Section */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center">
                    <span className="text-white text-sm font-bold">☁️</span>
                  </div>
                  <h3 className="text-lg font-semibold text-white">
                    Google Cloud Translation
                  </h3>
                </div>
                <div className="pl-10 space-y-6 max-w-xl">
                  <div className="space-y-4">
                    <p className="text-sm text-slate-500">
                      Configure Google Cloud Translation API credentials. Upload
                      or paste your service account JSON file.
                    </p>
                  </div>

                  {/* Show configured status - animation based on server state only */}
                  <AnimatePresence mode="wait">
                    {settings?.google_cloud_configured ? (
                      <motion.div
                        key="google-configured"
                        initial={false}
                        animate={{ opacity: 1 }}
                        exit={{
                          opacity: 0,
                          y: -20,
                          transition: { duration: 0.2 },
                        }}
                        transition={{ duration: 0.2 }}
                        className="space-y-3"
                      >
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <Label className="text-xs uppercase tracking-wider text-slate-500">
                              Project ID
                            </Label>
                            <span
                              className={`px-2 py-0.5 text-xs rounded-full ${
                                settings?.google_cloud_valid === true
                                  ? "bg-emerald-500/20 text-emerald-400"
                                  : settings?.google_cloud_valid === false
                                    ? "bg-red-500/20 text-red-400"
                                    : "bg-yellow-500/20 text-yellow-400"
                              }`}
                            >
                              {settings?.google_cloud_valid === true
                                ? "Valid"
                                : settings?.google_cloud_valid === false
                                  ? "Invalid"
                                  : "Not Validated"}
                            </span>
                          </div>
                          <div className="relative group">
                            <div className="w-full pr-10 px-3 py-2 bg-slate-900/50 border border-slate-700 rounded-md font-mono text-sm text-slate-300 overflow-hidden text-ellipsis whitespace-nowrap">
                              {settings.google_cloud_project_id || "Unknown"}
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={(e) => handleGoogleRemoveRequest(e)}
                              className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-slate-500 hover:text-destructive hover:bg-transparent"
                              title="Remove configuration"
                            >
                              <Trash2 className="h-4 w-4" />
                              <span className="sr-only">Remove</span>
                            </Button>
                          </div>
                        </div>
                        {/* Error Message Display */}
                        {settings?.google_cloud_valid === false &&
                          settings.google_cloud_error && (
                            <Alert className="bg-red-900/20 border-red-800 text-red-200">
                              <AlertCircle className="h-4 w-4 stroke-red-400" />
                              <AlertDescription className="ml-2 font-mono text-xs break-all">
                                {settings.google_cloud_error}
                              </AlertDescription>
                            </Alert>
                          )}
                      </motion.div>
                    ) : (
                      <motion.div
                        key="google-upload"
                        initial={false}
                        animate={{ opacity: 1 }}
                        exit={{
                          opacity: 0,
                          y: -20,
                          transition: { duration: 0.2 },
                        }}
                        transition={{ duration: 0.2 }}
                        className="space-y-4"
                      >
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <Label className="text-xs uppercase tracking-wider text-slate-500">
                              JSON Config
                            </Label>
                            <span
                              className={`px-2 py-0.5 text-xs rounded-full ${
                                settings?.google_cloud_valid === true
                                  ? "bg-emerald-500/20 text-emerald-400"
                                  : settings?.google_cloud_valid === false
                                    ? "bg-red-500/20 text-red-400"
                                    : "bg-yellow-500/20 text-yellow-400"
                              }`}
                            >
                              {settings?.google_cloud_valid === true
                                ? "Valid"
                                : settings?.google_cloud_valid === false
                                  ? "Invalid"
                                  : "Not Validated"}
                            </span>
                          </div>
                          <textarea
                            className="w-full h-32 bg-slate-900/50 border border-slate-700 rounded-md p-3 text-white placeholder:text-slate-500 font-mono text-xs resize-none focus:border-blue-500 focus:outline-none transition-all duration-300"
                            placeholder='{"type": "service_account", "project_id": "...", ...}'
                            onChange={(e) => {
                              updateField(
                                "google_cloud_credentials",
                                e.target.value,
                              );
                            }}
                          />
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-slate-500">or</span>
                          <label className="cursor-pointer group">
                            <input
                              type="file"
                              accept=".json"
                              className="hidden"
                              onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (file) {
                                  const reader = new FileReader();
                                  reader.onload = (event) => {
                                    const content = event.target?.result;
                                    if (typeof content === "string") {
                                      updateField(
                                        "google_cloud_credentials",
                                        content,
                                      );
                                    }
                                  };
                                  reader.readAsText(file);
                                }
                              }}
                            />
                            <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 rounded-lg text-white text-sm font-medium transition-all shadow-lg shadow-blue-500/20 group-hover:shadow-blue-500/40">
                              <svg
                                className="w-4 h-4"
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                                />
                              </svg>
                              Upload JSON
                            </div>
                          </label>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
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
            <CardContent className="space-y-6">
              <div className="pl-10 space-y-6 max-w-xl">
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-slate-500">
                    Host
                  </Label>
                  <Input
                    placeholder={settings?.qbittorrent_host || "Not configured"}
                    value={formData.qbittorrent_host || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_host", e.target.value)
                    }
                    onKeyDown={handleInputKeyDown}
                    className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 h-10 w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-slate-500">
                    Port
                  </Label>
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
                    onKeyDown={handleInputKeyDown}
                    className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 h-10 w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-slate-500">
                    Username
                  </Label>
                  <Input
                    placeholder={
                      settings?.qbittorrent_username || "Not configured"
                    }
                    value={formData.qbittorrent_username || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_username", e.target.value)
                    }
                    onKeyDown={handleInputKeyDown}
                    className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 h-10 w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-slate-500">
                    Password
                  </Label>
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
                    onKeyDown={handleInputKeyDown}
                    className="bg-slate-900/50 border-slate-700 text-white placeholder:text-slate-500 h-10 w-full"
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
            <CardContent className="space-y-6">
              <div className="pl-10 space-y-6 max-w-xl">
                <Alert className="bg-amber-900/10 border-amber-500/20 text-amber-200">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription className="ml-2">
                    Ensure the server has read/write permissions for these paths
                    at the filesystem level.
                  </AlertDescription>
                </Alert>
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-slate-500">
                    Paths (one per line)
                  </Label>
                  <textarea
                    className="w-full h-32 bg-slate-900/50 border border-slate-700 rounded-md p-3 text-white placeholder:text-slate-500 font-mono text-sm focus:border-amber-500 focus:outline-none transition-all duration-300"
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
              </div>
            </CardContent>
          </>
        )}
      </Card>

      <SavePill
        isVisible={hasChanges}
        isLoading={isSaving}
        hasChanges={hasChanges}
        onSave={handleSave}
        onDiscard={handleDiscard}
        isSuccess={!!success}
        containerRef={cardRef}
      />

      <ConfirmDialog
        key={`${confirmState.index}-${confirmState.targetRect?.top}`}
        open={confirmState.open}
        onOpenChange={(open) => setConfirmState((prev) => ({ ...prev, open }))}
        title={confirmState.title}
        description={confirmState.description}
        onConfirm={executeDelete}
        isLoading={isSaving}
        variant="destructive"
        confirmLabel="Remove"
        targetRect={confirmState.targetRect}
      />
    </div>
  );
}
