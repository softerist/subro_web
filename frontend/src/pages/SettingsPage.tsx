import { useEffect, useState, useRef } from "react";
import {
  AlertCircle,
  Check,
  Plus,
  Trash2,
  Copy,
  Eye,
  EyeOff,
  RefreshCw,
  Terminal,
  Plug,
  HardDrive,
  Settings,
} from "lucide-react";
import { usersApi } from "@/lib/users";
import { useAuthStore } from "@/store/authStore";
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
import { PageHeader } from "@/components/common/PageHeader";

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
  const [showApiKey, setShowApiKey] = useState(false);
  const [isGeneratingKey, setIsGeneratingKey] = useState(false);

  const { user, setUser } = useAuthStore();
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

  const tabs = [
    { id: "integrations", label: "API Integrations", icon: Plug },
    { id: "qbittorrent", label: "qBittorrent", icon: HardDrive },
  ] as const;

  const hasChanges = Object.keys(formData).length > 0;

  const handleRegenerateApiKey = async () => {
    try {
      setIsGeneratingKey(true);
      const updatedUser = await usersApi.regenerateApiKey();
      setUser({ ...user!, api_key: updatedUser.api_key });
      setSuccess("API Key regenerated successfully.");
      setTimeout(() => setSuccess(null), 3000);
    } catch (error) {
      setError("Failed to regenerate API key.");
      console.error(error);
    } finally {
      setIsGeneratingKey(false);
    }
  };

  const handleRevokeApiKey = async () => {
    try {
      setIsGeneratingKey(true);
      const updatedUser = await usersApi.revokeApiKey();
      setUser({ ...user!, api_key: updatedUser.api_key });
      setSuccess("API Key revoked successfully.");
      setTimeout(() => setSuccess(null), 3000);
    } catch (error) {
      setError("Failed to revoke API key.");
      console.error(error);
    } finally {
      setIsGeneratingKey(false);
    }
  };

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
        <div className="text-muted-foreground">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 px-4 pt-3 pb-3 page-enter page-stagger">
      <PageHeader
        title="Settings"
        description="Manage your application configuration"
        icon={Settings}
        iconClassName="from-amber-500 to-orange-500 shadow-amber-500/20"
      />

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert className="border-green-500/50 bg-green-500/10 text-green-400">
          <Check className="h-4 w-4" />
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-2 rounded-2xl border border-border bg-card/40 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id;
          const Icon = tab.icon;

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setCurrentTab(tab.id as SettingsTab)}
              className={`group relative flex-1 overflow-hidden rounded-xl px-4 py-2 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60 sm:text-sm ${
                isActive
                  ? "text-white"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/60"
              }`}
            >
              {isActive && (
                <motion.span
                  layoutId="settings-tab-indicator"
                  transition={{ type: "spring", stiffness: 420, damping: 32 }}
                  className="absolute inset-0 rounded-xl bg-gradient-to-r from-primary/90 via-sky-500/90 to-blue-600/90 shadow-lg shadow-sky-500/20 ring-1 ring-sky-400/40"
                />
              )}
              <span className="relative z-10 flex items-center justify-center gap-2">
                <Icon
                  className={`h-4 w-4 ${
                    isActive
                      ? "text-white"
                      : "text-muted-foreground group-hover:text-foreground"
                  }`}
                />
                <span className="whitespace-nowrap">{tab.label}</span>
              </span>
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <Card ref={cardRef} className="soft-hover bg-card/50 border-border">
        {/* API Integrations */}
        {currentTab === "integrations" && (
          <>
            <CardHeader>
              <CardTitle className="text-lg sm:text-xl font-bold title-gradient">
                External Services
              </CardTitle>
              <CardDescription className="text-muted-foreground">
                Configure API keys for metadata providers and subtitle services.
                Masked values indicate configured credentials from env.prod
                file.
              </CardDescription>

              <p className="mt-2 text-xs text-muted-foreground italic">
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
                  <h3 className="text-lg font-semibold text-foreground">
                    Metadata Providers
                  </h3>
                </div>
                <div className="pl-10 space-y-6 max-w-xl">
                  {/* TMDB API Key */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <Label
                          htmlFor="tmdb-api-key"
                          className="text-xs uppercase tracking-wider text-muted-foreground"
                        >
                          TMDB API Key
                        </Label>
                        {settings?.tmdb_api_key &&
                          settings.tmdb_api_key.trim() !== "" && (
                            <span className="text-xs text-muted-foreground">
                              (Free: ~40 req/10s)
                            </span>
                          )}
                      </div>
                      {settings?.tmdb_api_key &&
                      settings.tmdb_api_key.trim() !== "" ? (
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            settings?.tmdb_valid === "valid"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : settings?.tmdb_valid === "limit_reached"
                                ? "bg-amber-500/20 text-amber-400"
                                : settings?.tmdb_valid === "invalid"
                                  ? "bg-red-500/20 text-red-400"
                                  : "bg-amber-500/20 text-amber-500"
                          }`}
                        >
                          {settings?.tmdb_valid === "valid"
                            ? "Valid"
                            : settings?.tmdb_valid === "limit_reached"
                              ? "Limit Reached"
                              : settings?.tmdb_valid === "invalid"
                                ? "Invalid"
                                : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">
                          Not Connected
                        </span>
                      )}
                    </div>
                    <Input
                      id="tmdb-api-key"
                      name="tmdb_api_key"
                      placeholder={settings?.tmdb_api_key || "Enter API key..."}
                      value={formData.tmdb_api_key || ""}
                      onChange={(e) =>
                        updateField("tmdb_api_key", e.target.value)
                      }
                      onKeyDown={handleInputKeyDown}
                      className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                    />
                  </div>

                  {/* OMDB API Key */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <Label
                          htmlFor="omdb-api-key"
                          className="text-xs uppercase tracking-wider text-muted-foreground"
                        >
                          OMDB API Key
                        </Label>
                        {/* Free tier quota hint - always show when key is configured */}
                        {settings?.omdb_api_key &&
                          settings.omdb_api_key.trim() !== "" && (
                            <span className="text-xs text-muted-foreground">
                              (Free: 1000/day)
                            </span>
                          )}
                      </div>
                      {settings?.omdb_api_key &&
                      settings.omdb_api_key.trim() !== "" ? (
                        <span
                          className={`px-2 py-0.5 text-xs rounded-full ${
                            settings?.omdb_valid === "valid"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : settings?.omdb_valid === "limit_reached"
                                ? "bg-amber-500/20 text-amber-400"
                                : settings?.omdb_valid === "invalid"
                                  ? "bg-red-500/20 text-red-400"
                                  : "bg-amber-500/20 text-amber-500"
                          }`}
                        >
                          {settings?.omdb_valid === "valid"
                            ? "Valid"
                            : settings?.omdb_valid === "limit_reached"
                              ? "Limit Reached"
                              : settings?.omdb_valid === "invalid"
                                ? "Invalid"
                                : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">
                          Not Connected
                        </span>
                      )}
                    </div>
                    <Input
                      id="omdb-api-key"
                      name="omdb_api_key"
                      placeholder={settings?.omdb_api_key || "Enter API key..."}
                      value={formData.omdb_api_key || ""}
                      onChange={(e) =>
                        updateField("omdb_api_key", e.target.value)
                      }
                      onKeyDown={handleInputKeyDown}
                      className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                    />
                  </div>
                </div>
              </div>

              {/* OpenSubtitles Section */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
                    <span className="text-white text-sm font-bold">💬</span>
                  </div>
                  <h3 className="text-lg font-semibold text-foreground">
                    OpenSubtitles
                  </h3>
                  {/* Subscription tier badge */}
                  {settings?.opensubtitles_level && (
                    <span
                      className={`ml-1 px-2 py-0.5 text-xs rounded-full ${
                        settings.opensubtitles_vip
                          ? "bg-amber-500/20 text-amber-400"
                          : "bg-muted/50 text-muted-foreground"
                      }`}
                    >
                      {settings.opensubtitles_level}
                    </span>
                  )}
                  {/* Downloads allowance */}
                  {settings?.opensubtitles_allowed_downloads && (
                    <span className="text-xs text-muted-foreground">
                      ({settings.opensubtitles_allowed_downloads}/day)
                    </span>
                  )}
                  {/* Rate limit warning */}
                  {settings?.opensubtitles_rate_limited && (
                    <span className="px-2 py-0.5 text-xs rounded-full bg-red-500/20 text-red-400">
                      Limit Reached
                    </span>
                  )}
                </div>
                <div className="pl-10 space-y-6 max-w-xl">
                  {/* API Key */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label
                        htmlFor="opensubtitles-api-key"
                        className="text-xs uppercase tracking-wider text-muted-foreground"
                      >
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
                                : "bg-amber-500/20 text-amber-500"
                          }`}
                        >
                          {settings?.opensubtitles_key_valid === true
                            ? "Valid"
                            : settings?.opensubtitles_key_valid === false
                              ? "Invalid"
                              : "Not Validated"}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">
                          Not Connected
                        </span>
                      )}
                    </div>
                    <Input
                      id="opensubtitles-api-key"
                      name="opensubtitles_api_key"
                      placeholder={
                        settings?.opensubtitles_api_key || "Enter API key..."
                      }
                      value={formData.opensubtitles_api_key || ""}
                      onChange={(e) =>
                        updateField("opensubtitles_api_key", e.target.value)
                      }
                      onKeyDown={handleInputKeyDown}
                      className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                    />
                  </div>

                  {/* OpenSubtitles Credentials */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs uppercase tracking-wider text-muted-foreground">
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
                                : "bg-amber-500/20 text-amber-500"
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
                        <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">
                          Not Connected
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label
                          htmlFor="opensubtitles-username"
                          className="text-[10px] uppercase tracking-widest text-muted-foreground"
                        >
                          Username
                        </Label>
                        <Input
                          id="opensubtitles-username"
                          name="opensubtitles_username"
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
                          className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                        />
                      </div>

                      <div className="space-y-2">
                        <Label
                          htmlFor="opensubtitles-password"
                          className="text-[10px] uppercase tracking-widest text-muted-foreground"
                        >
                          Password
                        </Label>
                        <Input
                          id="opensubtitles-password"
                          name="opensubtitles_password"
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
                          className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
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
                  <h3 className="text-lg font-semibold text-foreground">
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
                    <p className="text-sm text-muted-foreground">
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
                            className="space-y-3 p-4 bg-card/50 rounded-xl border border-border transition-all duration-300 hover:border-primary/30 hover:bg-card/70"
                          >
                            <div className="flex items-center justify-between mb-2">
                              <Label
                                htmlFor={`deepl-api-key-${index}`}
                                className="text-xs uppercase tracking-wider text-muted-foreground"
                              >
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
                                <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">
                                  Not Connected
                                </span>
                              ) : (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-500">
                                  Not Validated
                                </span>
                              )}
                            </div>

                            <div className="relative group">
                              {isEditing ? (
                                <Input
                                  id={`deepl-api-key-${index}`}
                                  name={`deepl_api_keys[${index}]`}
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
                                  className="w-full pr-10 bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary font-mono text-sm h-10 transition-all duration-300"
                                />
                              ) : (
                                <button
                                  type="button"
                                  className="w-full pr-10 px-3 py-2 bg-background border border-input rounded-md font-mono text-sm text-foreground overflow-hidden text-ellipsis whitespace-nowrap cursor-pointer hover:border-primary/40 hover:bg-accent/60 transition-colors text-left"
                                  onClick={() => setEditingKeyIndex(index)}
                                  title="Click to edit"
                                  aria-label={`Edit DeepL API key ${index + 1}`}
                                >
                                  {isMasked
                                    ? key
                                    : `${"•".repeat(Math.max(0, key.length - 8))}${key.slice(-8)}`}
                                </button>
                              )}

                              {/* Remove Button - Inside Field */}
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                onClick={(e) =>
                                  handleKeyDeleteRequest(index, e)
                                }
                                className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-transparent"
                                title="Remove key"
                              >
                                <Trash2 className="h-4 w-4" />
                                <span className="sr-only">Remove</span>
                              </Button>
                            </div>

                            {/* Usage Progress Bar - Integrated inside */}
                            {usage && (
                              <div className="mt-2 space-y-1">
                                <div className="flex justify-between items-center text-[10px] text-muted-foreground">
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
                                    <div className="h-1 rounded-full bg-muted/70 overflow-hidden">
                                      <div
                                        className={`h-full transition-all duration-500 ${isFull ? "bg-destructive" : "bg-primary"}`}
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
                  <h3 className="text-lg font-semibold text-foreground">
                    Google Cloud Translation
                  </h3>
                </div>
                <div className="pl-10 space-y-6 max-w-xl">
                  <div className="space-y-4">
                    <p className="text-sm text-muted-foreground">
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
                            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                              Project ID
                            </Label>
                            <span
                              className={`px-2 py-0.5 text-xs rounded-full ${
                                settings?.google_cloud_valid === true
                                  ? "bg-emerald-500/20 text-emerald-400"
                                  : settings?.google_cloud_valid === false
                                    ? "bg-red-500/20 text-red-400"
                                    : "bg-amber-500/20 text-amber-500"
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
                            <div className="w-full pr-10 px-3 py-2 bg-background border border-input rounded-md font-mono text-sm text-foreground overflow-hidden text-ellipsis whitespace-nowrap">
                              {settings.google_cloud_project_id || "Unknown"}
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={(e) => handleGoogleRemoveRequest(e)}
                              className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-transparent"
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
                            <Alert className="bg-destructive/10 border-destructive/20 text-destructive">
                              <AlertCircle className="h-4 w-4 stroke-destructive" />
                              <AlertDescription className="ml-2 font-mono text-xs break-all">
                                {settings.google_cloud_error}
                              </AlertDescription>
                            </Alert>
                          )}
                        {/* Google Translate Usage Stats (from Cloud Monitoring API) */}
                        {settings?.google_usage && (
                          <div className="mt-4 p-3 rounded-lg border border-border/60 bg-muted/40">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs uppercase tracking-wider text-muted-foreground">
                                Translation Usage
                              </span>
                              {settings.google_usage.source ===
                              "google_cloud_monitoring" ? (
                                <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                  Live
                                </span>
                              ) : (
                                <div className="flex items-center gap-2">
                                  <span className="px-2 py-0.5 text-xs rounded-full bg-muted/70 text-muted-foreground border border-border/60">
                                    Local
                                  </span>
                                  <div
                                    className="group relative"
                                    title={
                                      settings.google_usage.last_updated
                                        ? `Last updated: ${new Date(settings.google_usage.last_updated).toLocaleString()}`
                                        : "Using cached data"
                                    }
                                  >
                                    <span className="px-2 py-0.5 text-xs rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30 cursor-help">
                                      API Unreachable
                                    </span>
                                  </div>
                                </div>
                              )}
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                              <div className="space-y-1">
                                <span className="text-xs text-muted-foreground">
                                  This Month
                                </span>
                                <div className="text-sm font-mono text-foreground">
                                  {settings.google_usage.this_month_characters.toLocaleString()}{" "}
                                  <span className="text-muted-foreground">
                                    chars
                                  </span>
                                </div>
                              </div>
                              <div className="space-y-1">
                                <span className="text-xs text-muted-foreground">
                                  All Time
                                </span>
                                <div className="text-sm font-mono text-foreground">
                                  {settings.google_usage.total_characters.toLocaleString()}{" "}
                                  <span className="text-muted-foreground">
                                    chars
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
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
                            <Label
                              htmlFor="google-cloud-config"
                              className="text-xs uppercase tracking-wider text-muted-foreground"
                            >
                              JSON Config
                            </Label>
                            <span
                              className={`px-2 py-0.5 text-xs rounded-full ${
                                settings?.google_cloud_valid === true
                                  ? "bg-emerald-500/20 text-emerald-400"
                                  : settings?.google_cloud_valid === false
                                    ? "bg-red-500/20 text-red-400"
                                    : "bg-amber-500/20 text-amber-500"
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
                            id="google-cloud-config"
                            name="google_cloud_credentials"
                            className="w-full h-32 bg-background border border-input rounded-md p-3 text-foreground placeholder:text-muted-foreground font-mono text-xs resize-none transition-colors hover:border-ring/40 hover:bg-accent/30 focus:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
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
                          <span className="text-xs text-muted-foreground">
                            or
                          </span>
                          <label className="cursor-pointer group">
                            <input
                              id="google-cloud-config-file"
                              name="google_cloud_credentials_file"
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
              <CardTitle className="text-lg sm:text-xl font-bold title-gradient">
                qBittorrent Settings
              </CardTitle>
              <CardDescription className="text-muted-foreground">
                Configure connection to your qBittorrent instance for torrent
                monitoring.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* API Key Section */}
              <div className="bg-card/50 rounded-lg p-4 border border-border">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                      <Terminal className="h-4 w-4 text-primary/80" />
                      Webhook Integration / API Key
                    </h4>
                    <p className="text-xs text-muted-foreground mt-1">
                      Use this key to trigger downloads from qBittorrent
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRegenerateApiKey}
                      disabled={isGeneratingKey}
                      className="h-8 border-emerald-400 text-emerald-600 hover:bg-emerald-50 hover:text-emerald-700 dark:border-blue-500 dark:text-blue-400 dark:bg-blue-500/25 dark:hover:bg-blue-500/40 dark:hover:text-blue-300"
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 mr-2 ${isGeneratingKey ? "animate-spin" : ""}`}
                      />
                      {user?.api_key ? "Regenerate" : "Generate"}
                    </Button>
                    {user?.api_key && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleRevokeApiKey}
                        disabled={isGeneratingKey}
                        className="h-8 border-destructive/50 text-destructive hover:bg-destructive/10 dark:border-red-500 dark:text-red-400 dark:bg-red-500/25 dark:hover:bg-red-500/40 dark:hover:text-red-300"
                      >
                        <Trash2 className="h-3.5 w-3.5 mr-2" />
                        Revoke
                      </Button>
                    )}
                  </div>
                </div>

                <div className="space-y-4">
                  {/* API Key Value */}
                  <div className="space-y-2">
                    <Label
                      htmlFor="qbittorrent-api-key"
                      className="text-xs uppercase tracking-wider text-muted-foreground"
                    >
                      Your API Key
                    </Label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <Input
                          id="qbittorrent-api-key"
                          name="api_key"
                          readOnly
                          value={
                            user?.api_key ||
                            "No API key generated — click Generate to create one"
                          }
                          type={
                            user?.api_key && !showApiKey ? "password" : "text"
                          }
                          className={`font-mono bg-background border-input pr-10 ${user?.api_key ? "text-foreground" : "text-muted-foreground italic"}`}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="absolute right-0 top-0 h-full text-muted-foreground hover:text-foreground"
                          onClick={() => setShowApiKey(!showApiKey)}
                          disabled={!user?.api_key}
                          aria-label={
                            showApiKey ? "Hide API key" : "Show API key"
                          }
                        >
                          {showApiKey ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                      <Button
                        variant="secondary"
                        size="icon"
                        className="bg-secondary/70 hover:bg-secondary text-secondary-foreground"
                        onClick={() => {
                          if (user?.api_key) {
                            navigator.clipboard.writeText(user.api_key);
                            setSuccess("API Key copied to clipboard.");
                            setTimeout(() => setSuccess(null), 2000);
                          }
                        }}
                        disabled={!user?.api_key}
                        aria-label="Copy API key"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  {/* qBittorrent Command Helper */}
                  {user?.api_key && (
                    <div className="space-y-2">
                      <Label className="text-xs tracking-wider text-muted-foreground flex items-center justify-between">
                        <span>
                          qBittorrent Command (&quot;Run external program&quot;)
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          Click to copy
                        </span>
                      </Label>
                      <div
                        className="rounded-md border border-emerald-200 dark:border-sky-900/50 bg-emerald-50 dark:bg-sky-950/30 p-3 font-mono text-xs text-emerald-900 dark:text-sky-200 break-all cursor-pointer transition-colors hover:bg-emerald-100 dark:hover:bg-sky-950/50 hover:border-emerald-300 dark:hover:border-sky-800"
                        onClick={() => {
                          const cmd = `curl -X POST ${window.location.origin}/api/v1/jobs/ -H "X-API-Key: ${user.api_key}" -H "Content-Type: application/json" -d "{\\"folder_path\\": \\"%R/%N\\", \\"log_level\\": \\"INFO\\"}"`;
                          navigator.clipboard.writeText(cmd);
                          setSuccess("Command copied to clipboard.");
                          setTimeout(() => setSuccess(null), 2000);
                        }}
                      >
                        curl -X POST {window.location.origin}/api/v1/jobs/ \
                        <br />
                        &nbsp;&nbsp;-H &quot;X-API-Key: {user.api_key}&quot; \
                        <br />
                        &nbsp;&nbsp;-H &quot;Content-Type:
                        application/json&quot; \<br />
                        &nbsp;&nbsp;-d &quot;&#123;\&quot;folder_path\&quot;:
                        \&quot;%R/%N\&quot;, \&quot;log_level\&quot;:
                        \&quot;INFO\&quot;&#125;&quot;
                      </div>
                      <p className="text-[10px] text-muted-foreground">
                        Note: Replace <code>%R/%N</code> with qBittorrent&apos;s
                        path variables if needed (e.g., <code>%D/%N</code> or{" "}
                        <code>%F</code>).
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div className="pl-10 space-y-6 max-w-xl">
                <div className="space-y-2">
                  <Label
                    htmlFor="qbittorrent-host"
                    className="text-xs uppercase tracking-wider text-muted-foreground"
                  >
                    Host
                  </Label>
                  <Input
                    id="qbittorrent-host"
                    name="qbittorrent_host"
                    placeholder={settings?.qbittorrent_host || "Not configured"}
                    value={formData.qbittorrent_host || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_host", e.target.value)
                    }
                    onKeyDown={handleInputKeyDown}
                    className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label
                    htmlFor="qbittorrent-port"
                    className="text-xs uppercase tracking-wider text-muted-foreground"
                  >
                    Port
                  </Label>
                  <Input
                    id="qbittorrent-port"
                    name="qbittorrent_port"
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
                    className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label
                    htmlFor="qbittorrent-username"
                    className="text-xs uppercase tracking-wider text-muted-foreground"
                  >
                    Username
                  </Label>
                  <Input
                    id="qbittorrent-username"
                    name="qbittorrent_username"
                    placeholder={
                      settings?.qbittorrent_username || "Not configured"
                    }
                    value={formData.qbittorrent_username || ""}
                    onChange={(e) =>
                      updateField("qbittorrent_username", e.target.value)
                    }
                    onKeyDown={handleInputKeyDown}
                    autoComplete="off"
                    className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label
                    htmlFor="qbittorrent-password"
                    className="text-xs uppercase tracking-wider text-muted-foreground"
                  >
                    Password
                  </Label>
                  <Input
                    id="qbittorrent-password"
                    name="qbittorrent_password"
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
                    autoComplete="new-password"
                    className="bg-background border-input text-foreground placeholder:text-muted-foreground focus:border-primary h-10 w-full"
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
