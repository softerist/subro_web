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
  ShieldCheck,
  Code2,
  ArrowUpRight,
} from "lucide-react";
import { FlowDiagram } from "@/components/common/FlowDiagram";
import { HelpIcon } from "@/components/common/HelpIcon";
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
import { MfaSettings } from "@/features/auth/components/MfaSettings";
import { PasswordSettings } from "@/features/auth/components/PasswordSettings";

type SettingsTab = "integrations" | "qbittorrent" | "developer" | "security";

export default function SettingsPage() {
  const { user, setUser } = useAuthStore();
  const isAdmin = user?.role === "admin" || user?.is_superuser;
  const [currentTab, setCurrentTab] = useState<SettingsTab>(
    isAdmin ? "integrations" : "security",
  );
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
  const [generatedApiKey, setGeneratedApiKey] = useState<string | null>(null);
  const [exampleTab, setExampleTab] = useState<"curl" | "python" | "node">(
    "curl",
  );

  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    type: "deepl" | "google" | "regenerate_api" | null;
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
    { id: "developer", label: "Developer API", icon: Code2 },
    { id: "security", label: "Security", icon: ShieldCheck },
  ].filter((tab) => (isAdmin ? true : tab.id === "security"));

  const hasChanges = Object.keys(formData).length > 0;

  const handleRegenerateApiKey = async () => {
    setConfirmState({
      open: true,
      type: "regenerate_api",
      title: "Confirm API Key Regeneration",
      description: (
        <div className="space-y-2">
          <p>Are you sure you want to regenerate your API key?</p>
          <p className="text-sm font-bold text-destructive">
            This will immediately invalidate the current key. Any scripts or
            integrations using it will stop working until updated.
          </p>
        </div>
      ),
    });
  };

  const handleRevokeApiKey = async () => {
    try {
      setIsGeneratingKey(true);
      await usersApi.revokeApiKey();
      setGeneratedApiKey(null);
      setShowApiKey(false);
      setUser({ ...user!, api_key_preview: null });
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
    if (isAdmin) {
      loadSettings();
    } else {
      setIsLoading(false);
      setCurrentTab("security");
    }
  }, [isAdmin]);

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
    } catch (_err) {
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
    } catch (_err) {
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

  const executeConfirm = async () => {
    setIsSaving(true);
    // Don't close immediately if we want to show loading state in dialog,
    // but typically we close and show global loading or keep it open.
    // The ConfirmDialog component handles isLoading prop by showing spinner on confirm button.
    // So we keep it open until success.

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
      } else if (confirmState.type === "regenerate_api") {
        // API Key Regeneration
        setIsGeneratingKey(true); // Local loading state for visual feedback elsewhere if needed
        const createdKey = await usersApi.regenerateApiKey();
        setGeneratedApiKey(createdKey.api_key);
        setShowApiKey(true);
        setUser({ ...user!, api_key_preview: createdKey.preview });
        successMsg = "API key generated. This value is shown only once.";
        // No updateSettings call needed here as it's a separate API endpoint
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
      }

      setSuccess(successMsg);
      // Close dialog on success
      setConfirmState((prev) => ({ ...prev, open: false, type: null }));
      setTimeout(() => setSuccess(null), 3000);
    } catch (_err) {
      setError("Failed to execute action.");
      // Close dialog on error? Or let user retry? Let's keep open on error but standard is close.
      setConfirmState((prev) => ({ ...prev, open: false, type: null }));
    } finally {
      setIsSaving(false);
      setIsGeneratingKey(false);
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
        description={
          isAdmin
            ? "Manage your application configuration"
            : "Manage your account security"
        }
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
                          className="text-xs uppercase tracking-wider text-muted-foreground cursor-pointer"
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
                          className="text-xs uppercase tracking-wider text-muted-foreground cursor-pointer"
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
                        className="text-xs uppercase tracking-wider text-muted-foreground cursor-pointer"
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
                      <h4 className="text-xs uppercase tracking-wider text-muted-foreground">
                        Credentials
                      </h4>
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
                                htmlFor={`deepl-api-key-input-${index}`}
                                className="text-xs uppercase tracking-wider text-muted-foreground cursor-pointer"
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
                                  id={`deepl-api-key-input-${index}`}
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
                                <div
                                  id={`deepl-api-key-input-${index}`}
                                  className="w-full pr-10 px-3 py-2 bg-background border border-input rounded-md font-mono text-sm text-foreground overflow-hidden text-ellipsis whitespace-nowrap cursor-pointer hover:border-primary/40 hover:bg-accent/60 transition-colors text-left"
                                  onClick={() => setEditingKeyIndex(index)}
                                  title="Click to edit"
                                  role="button"
                                  tabIndex={0}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter" || e.key === " ") {
                                      e.preventDefault();
                                      setEditingKeyIndex(index);
                                    }
                                  }}
                                  aria-label={`Edit DeepL API key ${index + 1}`}
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
                            <h4 className="text-xs uppercase tracking-wider text-muted-foreground">
                              Project ID
                            </h4>
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
                            placeholder="Paste your Google Cloud service account JSON here..."
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
            <CardHeader className="pb-4">
              <CardTitle className="text-xl sm:text-2xl font-bold title-gradient flex items-center gap-2">
                qBittorrent Integration
                <HelpIcon tooltip="Connect Subro to your qBittorrent client for automatic subtitle management." />
              </CardTitle>
              <CardDescription className="text-muted-foreground">
                Automate subtitle downloads whenever a new torrent completes.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-8">
              {/* Hero Status Section */}
              <div className="relative overflow-hidden rounded-2xl border border-emerald-500/20 bg-emerald-500/5 dark:bg-emerald-500/10 p-6">
                <div className="relative z-10 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="h-12 w-12 rounded-full bg-emerald-500/20 flex items-center justify-center animate-pulse-subtle">
                      <Check className="h-6 w-6 text-emerald-500" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded-full bg-emerald-500 text-white text-[10px] font-bold uppercase tracking-wider">
                          Active
                        </span>
                        <h4 className="text-lg font-bold text-foreground">
                          Webhook Ready
                        </h4>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        Subro is listening for completion events.
                        <HelpIcon tooltip="The webhook secret has been auto-generated and the API is ready to receive requests." />
                      </p>
                    </div>
                  </div>
                </div>
                {/* Decorative background element */}
                <div className="absolute -right-8 -bottom-8 h-32 w-32 bg-emerald-500/10 blur-3xl rounded-full" />
              </div>

              {/* Visual Flow Diagram */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                    Data Flow
                  </h4>
                  <HelpIcon tooltip="How information moves from your torrent client to the subtitle download." />
                </div>
                <FlowDiagram isActive={true} />
              </div>

              {/* Setup Guide */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                    Setup Guide
                  </h4>
                  <HelpIcon tooltip="Follow these steps to configure your qBittorrent instance." />
                </div>

                <div className="grid gap-4">
                  <div className="rounded-xl border border-border bg-card/50 p-4 hover:border-emerald-500/30 transition-colors group">
                    <div className="flex gap-4">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-600 font-bold text-sm">
                        1
                      </div>
                      <div className="flex-1">
                        <h5 className="text-sm font-bold text-foreground mb-1">
                          Place Webhook Script
                        </h5>
                        <p className="text-xs text-muted-foreground mb-3">
                          The script is located at:{" "}
                          <code className="bg-muted px-1 rounded">
                            /app/scripts/qbittorrent-nox-webhook.sh
                          </code>{" "}
                          inside the container.
                          <HelpIcon tooltip="This script is already mounted to your server's host system by default." />
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border border-border bg-card/50 p-4 hover:border-emerald-500/30 transition-colors group">
                    <div className="flex gap-4">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-600 font-bold text-sm">
                        2
                      </div>
                      <div className="flex-1">
                        <h5 className="text-sm font-bold text-foreground mb-1">
                          Configure qBittorrent
                        </h5>
                        <p className="text-xs text-muted-foreground mb-3">
                          Go to{" "}
                          <span className="font-semibold">
                            Tools › Options › Downloads › Run external program
                            on torrent completion
                          </span>
                          .
                        </p>
                        <div className="space-y-2">
                          <Label className="text-[10px] uppercase font-bold text-muted-foreground flex items-center justify-between">
                            Command to Paste
                            <span
                              className="text-emerald-500 cursor-pointer hover:underline"
                              onClick={async () => {
                                const cmd = `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`;
                                try {
                                  await navigator.clipboard.writeText(cmd);
                                  setSuccess("Command copied!");
                                  setTimeout(() => setSuccess(null), 2000);
                                } catch (e) {
                                  console.error(e);
                                }
                              }}
                            >
                              Click to copy
                            </span>
                          </Label>
                          <div
                            className="p-3 bg-muted/50 rounded-lg font-mono text-xs border border-border cursor-pointer hover:bg-muted transition-colors break-all"
                            onClick={async () => {
                              const cmd = `/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`;
                              try {
                                await navigator.clipboard.writeText(cmd);
                                setSuccess("Command copied!");
                                setTimeout(() => setSuccess(null), 2000);
                              } catch (e) {
                                console.error(e);
                              }
                            }}
                          >
                            {`/usr/bin/bash /opt/subro_web/scripts/qbittorrent-nox-webhook.sh "%F"`}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-4 space-y-6 max-w-xl">
                <div className="flex items-center gap-2 mb-2">
                  <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                    qBittorrent connection (Optional)
                  </h4>
                  <HelpIcon tooltip="These credentials allow Subro to manually query your qBittorrent instance if needed." />
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
                      placeholder={
                        settings?.qbittorrent_host || "Not configured"
                      }
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
              </div>
            </CardContent>
          </>
        )}

        {/* Developer API */}
        {currentTab === "developer" && (
          <>
            <CardHeader className="pb-4">
              <CardTitle className="text-xl sm:text-2xl font-bold title-gradient flex items-center gap-2">
                Developer API
                <HelpIcon tooltip="Your secret key for programmatic access to the Subro API." />
              </CardTitle>
              <CardDescription className="text-muted-foreground">
                Build custom integrations and automate subtitle workflows.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-8">
              {/* API Key Card */}
              <div className="bg-card/50 rounded-2xl border border-border p-6 shadow-sm">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                  <div>
                    <h4 className="text-lg font-bold text-foreground flex items-center gap-2">
                      <Terminal className="h-5 w-5 text-primary/80" />
                      Authentication Key
                    </h4>
                    <p className="text-sm text-muted-foreground mt-1">
                      Include this in the{" "}
                      <code className="bg-muted px-1 rounded text-xs">
                        X-API-Key
                      </code>{" "}
                      header.
                      <HelpIcon tooltip="Never share this key publicly. It provides full access to your account's job management." />
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRegenerateApiKey}
                      disabled={isGeneratingKey}
                      className="h-9 border-primary/30 hover:border-primary/50 transition-all font-medium"
                    >
                      <RefreshCw
                        className={`h-4 w-4 mr-2 ${isGeneratingKey ? "animate-spin" : ""}`}
                      />
                      {user?.api_key_preview ? "Regenerate" : "Generate"}
                    </Button>
                    {(user?.api_key_preview || generatedApiKey) && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleRevokeApiKey}
                        disabled={isGeneratingKey}
                        className="h-9 border-destructive/30 text-destructive hover:bg-destructive/10 dark:hover:bg-destructive/20 transition-all"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Revoke
                      </Button>
                    )}
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="relative group">
                    <Input
                      id="developer-api-key"
                      readOnly
                      value={
                        generatedApiKey ||
                        user?.api_key_preview ||
                        "No API key generated — click Generate to create one"
                      }
                      type={
                        generatedApiKey && !showApiKey ? "password" : "text"
                      }
                      className={`font-mono bg-background/80 border-input pr-24 h-12 text-sm ${generatedApiKey || user?.api_key_preview ? "text-foreground" : "text-muted-foreground italic"}`}
                    />
                    <div className="absolute right-0 top-0 h-full flex items-center pr-2 gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={() => setShowApiKey(!showApiKey)}
                        disabled={!generatedApiKey}
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
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={async () => {
                          if (generatedApiKey) {
                            try {
                              await navigator.clipboard.writeText(
                                generatedApiKey,
                              );
                              setSuccess("Copied!");
                              setTimeout(() => setSuccess(null), 2000);
                            } catch (err) {
                              console.error(err);
                            }
                          }
                        }}
                        disabled={!generatedApiKey}
                        aria-label="Copy API key"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  {generatedApiKey && (
                    <div className="px-1" aria-live="polite">
                      <p className="text-xs font-semibold text-foreground flex items-center gap-2">
                        <span>New key:</span>
                        <code className="rounded bg-muted px-2 py-1 font-mono break-all">
                          {generatedApiKey}
                        </code>
                      </p>
                    </div>
                  )}
                  <div className="flex items-center justify-between px-1">
                    <p className="text-[11px] text-muted-foreground">
                      {generatedApiKey
                        ? "✓ Key generated. Copy it now, it won't be shown again."
                        : user?.api_key_preview
                          ? "Authentication key is configured and active."
                          : "Start by generating a new developer key."}
                    </p>
                    <HelpIcon tooltip="Only a preview is stored for existing keys. Regenerating allows you to see the full key again." />
                  </div>
                </div>
              </div>

              {/* Quick Start Examples */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                    Quick Start Examples
                  </h4>
                  <HelpIcon tooltip="Ready-to-use code snippets for common integrations." />
                </div>

                <div className="rounded-2xl border border-border bg-card overflow-hidden">
                  <div className="flex border-b border-border bg-muted/30">
                    <button
                      onClick={() => setExampleTab("curl")}
                      className={`px-4 py-2.5 text-xs font-bold transition-all ${
                        exampleTab === "curl"
                          ? "border-b-2 border-primary text-primary bg-background/50"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      cURL
                    </button>
                    <button
                      onClick={() => setExampleTab("python")}
                      className={`px-4 py-2.5 text-xs font-bold transition-all ${
                        exampleTab === "python"
                          ? "border-b-2 border-primary text-primary bg-background/50"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      Python
                    </button>
                    <button
                      onClick={() => setExampleTab("node")}
                      className={`px-4 py-2.5 text-xs font-bold transition-all ${
                        exampleTab === "node"
                          ? "border-b-2 border-primary text-primary bg-background/50"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      Node.js
                    </button>
                  </div>
                  <div className="p-4 bg-muted/20">
                    <div className="relative group">
                      <pre className="text-[11px] font-mono leading-relaxed text-foreground overflow-x-auto p-4 rounded-xl bg-background/50 border border-border/50">
                        {exampleTab === "curl" &&
                          `curl -X POST ${window.location.origin}/api/v1/jobs/ \\
  -H "X-API-Key: ${generatedApiKey || user?.api_key_preview || "YOUR_API_KEY"}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "folder_path": "/media/movies/Inception",
    "log_level": "INFO"
  }'`}
                        {exampleTab === "python" &&
                          `import requests

url = "${window.location.origin}/api/v1/jobs/"
headers = {
    "X-API-Key": "${generatedApiKey || user?.api_key_preview || "YOUR_API_KEY"}",
    "Content-Type": "application/json"
}
data = {
    "folder_path": "/media/movies/Inception",
    "log_level": "INFO"
}

response = requests.post(url, headers=headers, json=data)
print(response.json())`}
                        {exampleTab === "node" &&
                          `const axios = require('axios');

const url = '${window.location.origin}/api/v1/jobs/';
const headers = {
  'X-API-Key': '${generatedApiKey || user?.api_key_preview || "YOUR_API_KEY"}',
  'Content-Type': 'application/json'
};
const data = {
  folder_path: '/media/movies/Inception',
  log_level: 'INFO'
};

axios.post(url, data, { headers })
  .then(response => console.log(response.data))
  .catch(error => console.error(error));`}
                      </pre>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute right-2 top-2 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={async () => {
                          let code = "";
                          if (exampleTab === "curl") {
                            code = `curl -X POST ${window.location.origin}/api/v1/jobs/ \\
  -H "X-API-Key: ${generatedApiKey || user?.api_key_preview || "YOUR_API_KEY"}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "folder_path": "/media/movies/Inception",
    "log_level": "INFO"
  }'`;
                          } else if (exampleTab === "python") {
                            code = `import requests

url = "${window.location.origin}/api/v1/jobs/"
headers = {
    "X-API-Key": "${generatedApiKey || user?.api_key_preview || "YOUR_API_KEY"}",
    "Content-Type": "application/json"
}
data = {
    "folder_path": "/media/movies/Inception",
    "log_level": "INFO"
}

response = requests.post(url, headers=headers, json=data)
print(response.json())`;
                          } else if (exampleTab === "node") {
                            code = `const axios = require('axios');

const url = '${window.location.origin}/api/v1/jobs/';
const headers = {
  'X-API-Key': '${generatedApiKey || user?.api_key_preview || "YOUR_API_KEY"}',
  'Content-Type': 'application/json'
};
const data = {
  folder_path: '/media/movies/Inception',
  log_level: 'INFO'
};

axios.post(url, data, { headers })
  .then(response => console.log(response.data))
  .catch(error => console.error(error));`;
                          }
                          try {
                            await navigator.clipboard.writeText(code);
                            setSuccess("Snippet copied!");
                            setTimeout(() => setSuccess(null), 2000);
                          } catch (err) {
                            console.error(err);
                          }
                        }}
                        aria-label="Copy code snippet"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              </div>

              {/* API Documentation Card */}
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                    API Documentation
                  </h4>
                  <HelpIcon tooltip="View rate limits and more endpoints." />
                </div>
                <div className="rounded-xl border border-border p-4 bg-card/30">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <h5 className="text-sm font-bold flex items-center gap-2">
                        Interactive API Explorer
                        <HelpIcon tooltip="Explore all available endpoints in the interactive Swagger UI." />
                      </h5>
                      <p className="text-xs text-muted-foreground">
                        Access the full OpenAPI specification and test endpoints
                        directly.
                      </p>
                    </div>
                    <Button
                      variant="link"
                      className="text-primary font-bold flex items-center gap-2 p-0 h-auto"
                      asChild
                    >
                      <a href="/docs" target="_blank" rel="noopener noreferrer">
                        Open Docs
                        <div className="h-4 w-4 rounded-full bg-primary/10 flex items-center justify-center">
                          <ArrowUpRight className="h-3 w-3" />
                        </div>
                      </a>
                    </Button>
                  </div>

                  <div className="mt-6 pt-6 border-t border-border">
                    <div className="flex items-center justify-between mb-3 text-xs">
                      <span className="font-bold flex items-center gap-2 text-muted-foreground uppercase tracking-widest">
                        Rate Limits
                        <HelpIcon tooltip="Remaining requests per minute for your specific API key." />
                      </span>
                      <span className="font-mono text-primary">100 / min</span>
                    </div>
                    <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                      <div className="bg-primary h-full w-[10%]" />
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </>
        )}

        {/* Security Tab Content */}
        {currentTab === "security" && (
          <div className="space-y-6" ref={cardRef}>
            <PasswordSettings />
            <MfaSettings />
          </div>
        )}
      </Card>

      {isAdmin && (
        <SavePill
          isVisible={hasChanges}
          isLoading={isSaving}
          hasChanges={hasChanges}
          onSave={handleSave}
          onDiscard={handleDiscard}
          isSuccess={!!success}
          containerRef={cardRef}
        />
      )}

      {isAdmin && (
        <ConfirmDialog
          key={`${confirmState.index}-${confirmState.targetRect?.top}`}
          open={confirmState.open}
          onOpenChange={(open) =>
            setConfirmState((prev) => ({ ...prev, open }))
          }
          title={confirmState.title}
          description={confirmState.description}
          onConfirm={executeConfirm}
          isLoading={isSaving}
          variant={
            confirmState.type === "regenerate_api" ? "default" : "destructive"
          }
          confirmLabel={
            confirmState.type === "regenerate_api" ? "Regenerate" : "Remove"
          }
          targetRect={confirmState.targetRect}
        />
      )}
    </div>
  );
}
