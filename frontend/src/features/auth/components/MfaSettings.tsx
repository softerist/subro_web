// frontend/src/features/auth/components/MfaSettings.tsx
/**
 * MFA Settings Component
 *
 * Allows users to enable/disable MFA and manage trusted devices.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck,
  ShieldOff,
  Loader2,
  Copy,
  Check,
  Smartphone,
  Trash2,
  QrCode,
} from "lucide-react";

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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useAuthStore } from "@/store/authStore";
import { mfaApi, MfaSetupResponse } from "../api/mfa";

export function MfaSettings() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);
  const [setupData, setSetupData] = useState<MfaSetupResponse | null>(null);
  const [verifyCode, setVerifyCode] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [copiedCodes, setCopiedCodes] = useState(false);
  const [showDisableDialog, setShowDisableDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch MFA status
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["mfa-status", userId],
    queryFn: mfaApi.getStatus,
  });

  // Fetch trusted devices
  const { data: devices = [] } = useQuery({
    queryKey: ["trusted-devices", userId],
    queryFn: mfaApi.getTrustedDevices,
    enabled: status?.mfa_enabled,
  });

  // Setup mutation
  const setupMutation = useMutation({
    mutationFn: mfaApi.setup,
    onSuccess: (data) => {
      setSetupData(data);
      setError(null);
    },
    onError: (err: unknown) => {
      const errorMessage = (
        err as { response?: { data?: { detail?: string } } }
      )?.response?.data?.detail;
      setError(errorMessage || "Failed to start MFA setup");
    },
  });

  // Verify setup mutation
  const verifyMutation = useMutation({
    mutationFn: () =>
      mfaApi.verifySetup({
        secret: setupData!.secret,
        code: verifyCode,
        backup_codes: setupData!.backup_codes,
      }),
    onSuccess: () => {
      setSetupData(null);
      setVerifyCode("");
      queryClient.invalidateQueries({ queryKey: ["mfa-status", userId] });
    },
    onError: (err: unknown) => {
      const errorMessage = (
        err as { response?: { data?: { detail?: string } } }
      )?.response?.data?.detail;
      setError(errorMessage || "Invalid code");
    },
  });

  // Disable mutation
  const disableMutation = useMutation({
    mutationFn: () => mfaApi.disable(disablePassword),
    onSuccess: () => {
      setShowDisableDialog(false);
      setDisablePassword("");
      queryClient.invalidateQueries({ queryKey: ["mfa-status", userId] });
      queryClient.invalidateQueries({ queryKey: ["trusted-devices", userId] });
    },
    onError: (err: unknown) => {
      const errorMessage = (
        err as { response?: { data?: { detail?: string } } }
      )?.response?.data?.detail;
      setError(errorMessage || "Failed to disable MFA");
    },
  });

  // Revoke device mutation
  const revokeMutation = useMutation({
    mutationFn: mfaApi.revokeTrustedDevice,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trusted-devices", userId] });
    },
  });

  const handleCopyBackupCodes = () => {
    if (setupData) {
      navigator.clipboard.writeText(setupData.backup_codes.join("\n"));
      setCopiedCodes(true);
      setTimeout(() => setCopiedCodes(false), 2000);
    }
  };

  if (statusLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  // MFA Setup Flow
  if (setupData) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <QrCode className="h-5 w-5" />
            Set Up Two-Factor Authentication
          </CardTitle>
          <CardDescription>
            Scan the QR code with your authenticator app
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* QR Code */}
          <div className="flex justify-center">
            <div className="bg-white p-4 rounded-lg">
              <img
                src={setupData.qr_code}
                alt="MFA QR Code"
                className="w-48 h-48"
              />
            </div>
          </div>

          {/* Manual Entry */}
          <div className="text-center">
            <p className="text-sm text-muted-foreground mb-2">
              Or enter this secret manually:
            </p>
            <code className="bg-muted px-3 py-1 rounded text-sm font-mono">
              {setupData.secret}
            </code>
          </div>

          {/* Backup Codes */}
          <div className="border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium">Backup Codes</h4>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyBackupCodes}
              >
                {copiedCodes ? (
                  <Check className="h-4 w-4 mr-1" />
                ) : (
                  <Copy className="h-4 w-4 mr-1" />
                )}
                {copiedCodes ? "Copied!" : "Copy All"}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground mb-3">
              Save these codes in a secure place. Each can be used once if you
              lose access to your authenticator.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {setupData.backup_codes.map((code, i) => (
                <code
                  key={i}
                  className="bg-muted px-2 py-1 rounded text-sm font-mono"
                >
                  {code}
                </code>
              ))}
            </div>
          </div>

          {/* Verification Input */}
          <div className="space-y-2">
            <Label htmlFor="verify-code">Enter code from your app</Label>
            <Input
              id="verify-code"
              type="text"
              inputMode="numeric"
              placeholder="000000"
              value={verifyCode}
              onChange={(e) =>
                setVerifyCode(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              className="text-center text-xl tracking-widest font-mono"
              maxLength={6}
            />
          </div>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => {
                setSetupData(null);
                setVerifyCode("");
                setError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              className="flex-1"
              disabled={verifyCode.length < 6 || verifyMutation.isPending}
              onClick={() => verifyMutation.mutate()}
            >
              {verifyMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Enable MFA
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // MFA Status Display
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {status?.mfa_enabled ? (
            <ShieldCheck className="h-5 w-5 text-green-500" />
          ) : (
            <ShieldOff className="h-5 w-5 text-muted-foreground" />
          )}
          Two-Factor Authentication
        </CardTitle>
        <CardDescription>
          {status?.mfa_enabled
            ? "Your account is protected with MFA"
            : "Add an extra layer of security to your account"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {status?.mfa_enabled ? (
          <>
            {/* Enabled State */}
            <div className="flex items-center justify-between p-4 bg-green-500/10 border border-green-500/20 rounded-lg">
              <div className="flex items-center gap-3">
                <ShieldCheck className="h-8 w-8 text-green-500" />
                <div>
                  <p className="font-medium">MFA is enabled</p>
                  <p className="text-sm text-muted-foreground">
                    Your account is protected
                  </p>
                </div>
              </div>
              <Dialog
                open={showDisableDialog}
                onOpenChange={setShowDisableDialog}
              >
                <DialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    Disable
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>
                      Disable Two-Factor Authentication?
                    </DialogTitle>
                    <DialogDescription>
                      This will remove the extra security from your account.
                      Enter your password to confirm.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-2">
                    <Label htmlFor="disable-password">Password</Label>
                    <Input
                      id="disable-password"
                      type="password"
                      value={disablePassword}
                      onChange={(e) => setDisablePassword(e.target.value)}
                      placeholder="Enter your password"
                    />
                    {error && <p className="text-sm text-red-500">{error}</p>}
                  </div>
                  <DialogFooter>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowDisableDialog(false);
                        setDisablePassword("");
                        setError(null);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="destructive"
                      disabled={!disablePassword || disableMutation.isPending}
                      onClick={() => disableMutation.mutate()}
                    >
                      {disableMutation.isPending && (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      )}
                      Disable MFA
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>

            {/* Trusted Devices */}
            {devices.length > 0 && (
              <div className="space-y-3">
                <h4 className="font-medium flex items-center gap-2">
                  <Smartphone className="h-4 w-4" />
                  Trusted Devices ({devices.filter((d) => !d.is_expired).length}
                  )
                </h4>
                <div className="space-y-2">
                  {devices
                    .filter((d) => !d.is_expired)
                    .map((device) => (
                      <div
                        key={device.id}
                        className="flex items-center justify-between p-3 border rounded-lg text-sm"
                      >
                        <div>
                          <p className="font-medium truncate max-w-[200px]">
                            {device.device_name || "Unknown device"}
                          </p>
                          <p className="text-muted-foreground text-xs">
                            Last used:{" "}
                            {device.last_used_at
                              ? new Date(
                                  device.last_used_at,
                                ).toLocaleDateString()
                              : "Never"}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => revokeMutation.mutate(device.id)}
                          disabled={revokeMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            {/* Disabled State */}
            <div className="p-4 bg-muted/50 border rounded-lg">
              <p className="text-sm text-muted-foreground">
                Two-factor authentication adds an extra layer of security by
                requiring a code from your phone in addition to your password.
              </p>
            </div>
            <Button
              onClick={() => setupMutation.mutate()}
              disabled={setupMutation.isPending}
            >
              {setupMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ShieldCheck className="mr-2 h-4 w-4" />
              )}
              Enable Two-Factor Authentication
            </Button>
            {error && <p className="text-sm text-red-500">{error}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
