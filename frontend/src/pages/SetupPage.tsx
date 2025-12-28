import { useState } from "react";
import { useNavigate } from "react-router-dom";
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
  completeSetup,
  skipSetup,
  SetupComplete,
  SettingsUpdate,
} from "@/lib/settingsApi";
import { useSettingsStore } from "@/store/settingsStore";

type SetupStep = "welcome" | "admin" | "integrations" | "finish";

export default function SetupPage() {
  const navigate = useNavigate();
  const setSetupCompleted = useSettingsStore(
    (state) => state.setSetupCompleted,
  );

  const [currentStep, setCurrentStep] = useState<SetupStep>("welcome");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Admin form state
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // Settings form state
  const [settings, setSettings] = useState<SettingsUpdate>({
    tmdb_api_key: "",
    omdb_api_key: "",
    opensubtitles_api_key: "",
    opensubtitles_username: "",
    opensubtitles_password: "",
    deepl_api_keys: [],
    qbittorrent_host: "",
    qbittorrent_port: undefined,
    qbittorrent_username: "",
    qbittorrent_password: "",
  });

  const handleNext = () => {
    if (currentStep === "welcome") setCurrentStep("admin");
    else if (currentStep === "admin") {
      // Validate admin form
      if (!adminEmail || !adminPassword) {
        setError("Email and password are required");
        return;
      }
      // Validate email format (must have @ and a domain with a period)
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(adminEmail)) {
        setError("Please enter a valid email address (e.g., user@example.com)");
        return;
      }
      if (adminPassword !== confirmPassword) {
        setError("Passwords do not match");
        return;
      }
      if (adminPassword.length < 8) {
        setError("Password must be at least 8 characters");
        return;
      }
      setError(null);
      setCurrentStep("integrations");
    } else if (currentStep === "integrations") {
      setCurrentStep("finish");
    }
  };

  const handleBack = () => {
    if (currentStep === "admin") setCurrentStep("welcome");
    else if (currentStep === "integrations") setCurrentStep("admin");
    else if (currentStep === "finish") setCurrentStep("integrations");
  };

  const handleComplete = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Filter out empty settings
      const filteredSettings: SettingsUpdate = {};
      Object.entries(settings).forEach(([key, value]) => {
        if (value !== "" && value !== undefined && value !== null) {
          (filteredSettings as Record<string, unknown>)[key] = value;
        }
      });

      const data: SetupComplete = {
        admin_email: adminEmail,
        admin_password: adminPassword,
        settings:
          Object.keys(filteredSettings).length > 0
            ? filteredSettings
            : undefined,
      };

      await completeSetup(data);
      setSetupCompleted(true);
      navigate("/login");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Setup failed. Please try again.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkip = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Skip but still create admin if provided
      if (adminEmail && adminPassword) {
        await skipSetup(adminEmail, adminPassword);
      } else {
        await skipSetup();
      }
      setSetupCompleted(true);
      navigate("/login");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Skip failed. Please try again.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const updateSetting = (
    key: keyof SettingsUpdate,
    value: string | number | string[],
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4 page-enter">
      <div className="w-full max-w-lg page-stagger">
        {/* Progress indicator */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center gap-2">
            {["welcome", "admin", "integrations", "finish"].map(
              (step, index) => (
                <div key={step} className="flex items-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                      currentStep === step
                        ? "bg-primary text-primary-foreground"
                        : index <
                            [
                              "welcome",
                              "admin",
                              "integrations",
                              "finish",
                            ].indexOf(currentStep)
                          ? "bg-green-600 text-white"
                          : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {index + 1}
                  </div>
                  {index < 3 && <div className="w-8 h-0.5 bg-muted" />}
                </div>
              ),
            )}
          </div>
        </div>

        <Card className="bg-card/50 border-border backdrop-blur soft-hover">
          {/* Welcome Step */}
          {currentStep === "welcome" && (
            <>
              <CardHeader className="text-center">
                <CardTitle className="text-2xl sm:text-3xl text-card-foreground">
                  Welcome to Subro Web
                </CardTitle>
                <CardDescription className="text-muted-foreground">
                  Let&apos;s set up your subtitle download manager. This wizard
                  will help you configure the admin account and optional
                  integrations.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center text-muted-foreground text-sm">
                  <p>You&apos;ll configure:</p>
                  <ul className="mt-2 space-y-1">
                    <li>✓ Admin account credentials</li>
                    <li>✓ API keys for subtitle providers (optional)</li>
                    <li>✓ Google Cloud Translation credentials (optional)</li>
                    <li>✓ qBittorrent integration (optional)</li>
                  </ul>
                </div>
                <div className="flex justify-between pt-4">
                  <Button
                    variant="ghost"
                    onClick={handleSkip}
                    disabled={isLoading}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    Skip Setup
                  </Button>
                  <Button
                    onClick={handleNext}
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    Get Started
                  </Button>
                </div>
              </CardContent>
            </>
          )}

          {/* Admin Step */}
          {currentStep === "admin" && (
            <>
              <CardHeader>
                <CardTitle className="text-xl sm:text-2xl text-card-foreground">
                  Create Admin Account
                </CardTitle>
                <CardDescription className="text-muted-foreground">
                  Set up the administrator account for managing the application.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleNext();
                  }}
                  className="space-y-4"
                >
                  {error && (
                    <Alert variant="destructive">
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  )}
                  <div className="space-y-2">
                    <Label htmlFor="email" className="text-muted-foreground">
                      Email
                    </Label>
                    <Input
                      id="email"
                      type="email"
                      value={adminEmail}
                      onChange={(e) => setAdminEmail(e.target.value)}
                      placeholder="admin@example.com"
                      className="bg-background border-input text-foreground"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password" className="text-muted-foreground">
                      Password
                    </Label>
                    <Input
                      id="password"
                      type="password"
                      value={adminPassword}
                      onChange={(e) => setAdminPassword(e.target.value)}
                      placeholder="••••••••"
                      className="bg-background border-input text-foreground"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor="confirmPassword"
                      className="text-muted-foreground"
                    >
                      Confirm Password
                    </Label>
                    <Input
                      id="confirmPassword"
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="bg-background border-input text-foreground"
                    />
                  </div>
                  <div className="flex justify-between pt-4">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={handleBack}
                      className="text-muted-foreground"
                    >
                      Back
                    </Button>
                    <Button type="submit" className="">
                      Continue
                    </Button>
                  </div>
                </form>
              </CardContent>
            </>
          )}

          {/* Integrations Step */}
          {currentStep === "integrations" && (
            <>
              <CardHeader>
                <CardTitle className="text-xl sm:text-2xl text-card-foreground">
                  Configure Integrations
                </CardTitle>
                <CardDescription className="text-muted-foreground">
                  Optional: Add your API keys for enhanced functionality. Leave
                  blank to use defaults from environment.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2">
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">
                      TMDB API Key
                    </Label>
                    <Input
                      value={settings.tmdb_api_key || ""}
                      onChange={(e) =>
                        updateSetting("tmdb_api_key", e.target.value)
                      }
                      placeholder="Leave blank to use default"
                      className="bg-background border-input text-foreground"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">
                      OMDB API Key
                    </Label>
                    <Input
                      value={settings.omdb_api_key || ""}
                      onChange={(e) =>
                        updateSetting("omdb_api_key", e.target.value)
                      }
                      placeholder="Leave blank to use default"
                      className="bg-background border-input text-foreground"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">
                      OpenSubtitles API Key
                    </Label>
                    <Input
                      value={settings.opensubtitles_api_key || ""}
                      onChange={(e) =>
                        updateSetting("opensubtitles_api_key", e.target.value)
                      }
                      placeholder="Leave blank to use default"
                      className="bg-background border-input text-foreground"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-muted-foreground">
                        OpenSubtitles Username
                      </Label>
                      <Input
                        value={settings.opensubtitles_username || ""}
                        onChange={(e) =>
                          updateSetting(
                            "opensubtitles_username",
                            e.target.value,
                          )
                        }
                        placeholder="Leave blank to use default"
                        className="bg-background border-input text-foreground"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-muted-foreground">
                        OpenSubtitles Password
                      </Label>
                      <Input
                        type="password"
                        value={settings.opensubtitles_password || ""}
                        onChange={(e) =>
                          updateSetting(
                            "opensubtitles_password",
                            e.target.value,
                          )
                        }
                        placeholder="Leave blank to use default"
                        className="bg-background border-input text-foreground"
                      />
                    </div>
                  </div>
                  <div className="border-t border-border pt-4 mt-4">
                    <p className="text-sm text-muted-foreground mb-3">
                      DeepL Translation (optional)
                    </p>
                    <div className="space-y-2">
                      <Label className="text-muted-foreground">
                        DeepL API Keys
                      </Label>
                      <textarea
                        value={(settings.deepl_api_keys || []).join("\n")}
                        onChange={(e) =>
                          updateSetting(
                            "deepl_api_keys",
                            e.target.value.split("\n").filter((k) => k.trim()),
                          )
                        }
                        placeholder="One API key per line (optional)"
                        className="w-full h-20 bg-background border border-input rounded-md p-2 text-foreground placeholder:text-muted-foreground text-sm font-mono transition-colors hover:border-ring/40 hover:bg-accent/30 focus:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                      />
                    </div>
                  </div>
                  <div className="border-t border-border pt-4 mt-4">
                    <p className="text-sm text-muted-foreground mb-3">
                      Google Cloud Translation (optional)
                    </p>
                    <div className="space-y-2">
                      <Label className="text-muted-foreground">
                        Service Account JSON Credentials
                      </Label>
                      <div className="flex items-center gap-2">
                        <label className="flex-1 cursor-pointer">
                          <div className="flex items-center justify-center px-4 py-3 bg-secondary border border-border border-dashed rounded-md text-muted-foreground hover:border-primary hover:text-primary transition-colors">
                            <svg
                              className="w-5 h-5 mr-2"
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
                            <span className="text-sm">
                              {settings.google_cloud_credentials
                                ? "✓ Credentials loaded"
                                : "Upload JSON file"}
                            </span>
                          </div>
                          <input
                            type="file"
                            accept=".json"
                            className="hidden"
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) {
                                const reader = new FileReader();
                                reader.onload = (event) => {
                                  const content = event.target
                                    ?.result as string;
                                  updateSetting(
                                    "google_cloud_credentials",
                                    content,
                                  );
                                };
                                reader.readAsText(file);
                              }
                            }}
                          />
                        </label>
                        {settings.google_cloud_credentials && (
                          <button
                            type="button"
                            onClick={() =>
                              updateSetting("google_cloud_credentials", "")
                            }
                            className="p-2 text-muted-foreground hover:text-destructive transition-colors"
                            title="Remove credentials"
                          >
                            <svg
                              className="w-5 h-5"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M6 18L18 6M6 6l12 12"
                              />
                            </svg>
                          </button>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Upload your Google Cloud service account JSON file
                      </p>
                    </div>
                  </div>
                  <div className="border-t border-border pt-4 mt-4">
                    <p className="text-sm text-muted-foreground mb-3">
                      qBittorrent (for torrent monitoring)
                    </p>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-muted-foreground">Host</Label>
                        <Input
                          value={settings.qbittorrent_host || ""}
                          onChange={(e) =>
                            updateSetting("qbittorrent_host", e.target.value)
                          }
                          placeholder="localhost"
                          className="bg-background border-input text-foreground"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-muted-foreground">Port</Label>
                        <Input
                          type="number"
                          value={settings.qbittorrent_port || ""}
                          onChange={(e) =>
                            updateSetting(
                              "qbittorrent_port",
                              parseInt(e.target.value) || 0,
                            )
                          }
                          placeholder="8080"
                          className="bg-background border-input text-foreground"
                        />
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex justify-between pt-4">
                  <Button
                    variant="ghost"
                    onClick={handleBack}
                    className="text-muted-foreground"
                  >
                    Back
                  </Button>
                  <Button onClick={handleNext} className="">
                    Continue
                  </Button>
                </div>
              </CardContent>
            </>
          )}

          {/* Finish Step */}
          {currentStep === "finish" && (
            <>
              <CardHeader className="text-center">
                <CardTitle className="text-xl sm:text-2xl text-card-foreground">
                  Ready to Go!
                </CardTitle>
                <CardDescription className="text-muted-foreground">
                  Your setup is complete. Click finish to save your
                  configuration and start using Subro Web.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
                <div className="bg-muted/50 rounded-lg p-4 space-y-2 text-sm">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Admin Email:</span>
                    <span className="text-foreground">{adminEmail}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>API Keys Configured:</span>
                    <span className="text-foreground">
                      {Object.values(settings).filter((v) => v).length} fields
                    </span>
                  </div>
                </div>
                <div className="flex justify-between pt-4">
                  <Button
                    variant="ghost"
                    onClick={handleBack}
                    className="text-muted-foreground"
                  >
                    Back
                  </Button>
                  <Button
                    onClick={handleComplete}
                    disabled={isLoading}
                    className=""
                  >
                    {isLoading ? "Saving..." : "Finish Setup"}
                  </Button>
                </div>
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
