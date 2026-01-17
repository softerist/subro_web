import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Loader2, ShieldCheck, ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/features/auth/api/auth";
import { cn } from "@/lib/utils";
import { api } from "@/lib/apiClient";

interface LoginResponse {
  access_token?: string;
  token_type?: string;
  requires_mfa?: boolean;
  message?: string;
}

export function LoginForm({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const [step, setStep] = useState<"email" | "password">("email");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  // MFA state
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaCode, setMfaCode] = useState("");
  const [trustDevice, setTrustDevice] = useState(false);

  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);

  // Handle successful login (with or without MFA)
  const handleLoginSuccess = async (accessToken: string) => {
    useAuthStore.getState().setAccessToken(accessToken);
    try {
      const user = await authApi.getMe();
      login(accessToken, {
        id: user.id,
        email: user.email,
        role: user.role ?? "user",
        api_key_preview: user.api_key_preview ?? null,
        is_superuser: user.is_superuser ?? false,
        force_password_change: user.force_password_change ?? false,
        preferences: user.preferences,
      });
      navigate("/dashboard");
    } catch (_err) {
      setError("Failed to fetch user profile.");
    }
  };

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: async (data: LoginResponse) => {
      if (data.requires_mfa) {
        // MFA is required, show MFA input
        setMfaRequired(true);
        setError(null);
      } else if (data.access_token) {
        // Check if admin needs to set up MFA
        if ("mfa_setup_required" in data && data.mfa_setup_required) {
          // Store flag for persistent warning banner
          localStorage.setItem("mfa_setup_required", "true");
        } else {
          localStorage.removeItem("mfa_setup_required");
        }
        // Normal login success
        await handleLoginSuccess(data.access_token);
      }
    },
    onError: (err: unknown) => {
      const axiosError = err as {
        response?: { data?: { detail?: string; error?: string } };
      };
      const detail =
        axiosError.response?.data?.detail ||
        axiosError.response?.data?.error ||
        null;

      if (detail === "LOGIN_BAD_CREDENTIALS") {
        setError("Invalid email or password.");
      } else if (detail === "LOGIN_ACCOUNT_SUSPENDED") {
        setError("Account suspended. Please contact support.");
      } else if (detail === "LOGIN_USER_INACTIVE") {
        setError("This account has been deactivated.");
      } else if (typeof detail === "string" && detail.includes("locked")) {
        setError(detail);
      } else if (typeof detail === "string" && detail.includes("Rate limit")) {
        setError("Too many attempts. Please wait a moment and try again.");
      } else {
        setError(detail || "Login failed. Please try again.");
      }
    },
  });

  // MFA verification mutation
  const mfaMutation = useMutation({
    mutationFn: async (data: { code: string; trust_device: boolean }) => {
      const response = await api.post("/v1/auth/mfa/verify", data);
      return response.data;
    },
    onSuccess: async (data: { access_token: string }) => {
      await handleLoginSuccess(data.access_token);
    },
    onError: (err: unknown) => {
      const axiosError = err as {
        response?: { data?: { detail?: string } };
      };
      const detail = axiosError.response?.data?.detail;

      if (detail === "MFA session not found. Please start login again.") {
        // Session expired, reset to login
        setMfaRequired(false);
        setMfaCode("");
        setError("Session expired. Please login again.");
      } else {
        setError(detail || "Invalid verification code.");
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (step === "email") {
      if (!email.trim()) {
        setError("Please enter your email.");
        return;
      }
      // Simple email regex validation
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email)) {
        setError("Please enter a valid email address.");
        return;
      }
      setStep("password");
    } else {
      loginMutation.mutate({ username: email, password });
    }
  };

  const handleBackToEmail = () => {
    setStep("email");
    setError(null);
    setPassword(""); // Optional: clear password when going back?
  };

  const handleMfaSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    mfaMutation.mutate({ code: mfaCode, trust_device: trustDevice });
  };

  const isLoading = loginMutation.isPending || mfaMutation.isPending;

  // MFA verification form
  if (mfaRequired) {
    return (
      <div className={cn("grid gap-6", className)} {...props}>
        <div className="flex flex-col items-center gap-2 text-center mb-4">
          <ShieldCheck className="h-12 w-12 text-primary" />
          <h2 className="text-lg font-semibold">Two-Factor Authentication</h2>
          <p className="text-sm text-muted-foreground">
            Enter the 6-digit code from your authenticator app
          </p>
        </div>
        <form onSubmit={handleMfaSubmit}>
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="mfa-code" className="text-foreground">
                Verification Code
              </Label>
              <Input
                id="mfa-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                value={mfaCode}
                onChange={(e) =>
                  setMfaCode(e.target.value.replace(/\D/g, "").slice(0, 8))
                }
                disabled={isLoading}
                className="text-center text-2xl tracking-widest font-mono"
                maxLength={8}
                autoFocus
                required
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="trust-device"
                checked={trustDevice}
                onCheckedChange={(checked) => setTrustDevice(checked === true)}
                disabled={isLoading}
              />
              <Label
                htmlFor="trust-device"
                className="text-sm text-muted-foreground cursor-pointer"
              >
                Trust this device for 30 days
              </Label>
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button disabled={isLoading || mfaCode.length < 6}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Verify
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setMfaRequired(false);
                setMfaCode("");
                setTrustDevice(false);
                setError(null);
              }}
              disabled={isLoading}
            >
              Back to Login
            </Button>
          </div>
        </form>
      </div>
    );
  }

  // Normal login form (Step-based)
  return (
    <div className={cn("grid gap-6", className)} {...props}>
      <form onSubmit={handleSubmit} action="/login" method="post">
        <div className={cn("grid gap-4")}>
          {step === "email" ? (
            <div className="grid gap-2 animate-in fade-in slide-in-from-right-4 duration-300">
              <Label htmlFor="email" className="text-foreground">
                Email
              </Label>
              <Input
                id="email"
                name="email"
                placeholder="name@example.com"
                type="email"
                autoCapitalize="none"
                autoComplete="username"
                autoCorrect="off"
                disabled={isLoading}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                required
              />
            </div>
          ) : (
            <div className="grid gap-4 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className="flex items-center justify-between p-2 border rounded-md bg-muted/20">
                <div className="text-sm font-medium truncate px-1">{email}</div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleBackToEmail}
                  className="h-8 text-xs text-muted-foreground hover:text-primary"
                >
                  Edit
                </Button>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="password" className="text-foreground">
                  Password
                </Label>
                <Input
                  id="password"
                  name="password"
                  placeholder="Password"
                  type="password"
                  autoComplete="current-password"
                  disabled={isLoading}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoFocus
                  required
                />
              </div>
              <div className="flex justify-end">
                <a
                  href="/forgot-password"
                  className="text-sm text-primary hover:underline"
                >
                  Forgot password?
                </a>
              </div>
            </div>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}

          <Button disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {step === "email" ? "Next" : "Sign In"}
          </Button>

          {step === "password" && (
            <Button
              type="button"
              variant="ghost"
              onClick={handleBackToEmail}
              disabled={isLoading}
              className="mt-[-0.5rem]"
            >
              <ArrowLeft className="mr-2 h-4 w-4" /> Back
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}
