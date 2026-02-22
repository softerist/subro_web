// frontend/src/components/auth/ReauthModal.tsx
/**
 * Reauth Modal Component
 *
 * Shows when a user needs to re-authenticate for sensitive operations
 * (e.g., managing passkeys after being logged in for a while)
 */

import { useState } from "react";
import { Loader2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { passkeyApi } from "@/features/auth/api/passkey";

interface ReauthModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  message?: string;
}

export function ReauthModal({
  open,
  onClose,
  onSuccess,
  message,
}: ReauthModalProps) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [usePasskey, setUsePasskey] = useState(false);

  const handlePasswordReauth = async () => {
    setError(null);
    setIsLoading(true);

    try {
      // Call your password verification endpoint
      // This should refresh the token with a new auth_time
      const response = await fetch("/api/v1/auth/verify-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (!response.ok) {
        throw new Error("Invalid password");
      }

      onSuccess();
      setPassword("");
      onClose();
    } catch (_err) {
      setError("Invalid password. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasskeyReauth = async () => {
    setError(null);
    setIsLoading(true);

    try {
      // Use passkey authentication which will refresh auth_time
      await passkeyApi.authenticate();
      onSuccess();
      onClose();
    } catch (_err) {
      setError("Passkey authentication failed. Please try password instead.");
      setUsePasskey(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (usePasskey) {
      handlePasskeyReauth();
    } else {
      handlePasswordReauth();
    }
  };

  return (
    <Dialog open={open} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-amber-600" />
            Verify Your Identity
          </DialogTitle>
          <DialogDescription>
            {message ||
              "For security, please verify your identity to continue."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4 py-4">
            {!usePasskey ? (
              <div className="space-y-2">
                <Label htmlFor="reauth-password">Password</Label>
                <Input
                  id="reauth-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  autoFocus
                  disabled={isLoading}
                />
              </div>
            ) : (
              <div className="p-4 bg-muted/50 border rounded-lg text-center">
                <p className="text-sm text-muted-foreground">
                  Click &quot;Verify with Passkey&quot; to authenticate with
                  biometrics
                </p>
              </div>
            )}

            {error && <p className="text-sm text-red-500">{error}</p>}

            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => setUsePasskey(!usePasskey)}
              disabled={isLoading}
            >
              {usePasskey ? "Use password instead" : "Use passkey instead"}
            </Button>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isLoading || (!usePasskey && !password.trim())}
            >
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {usePasskey ? "Verify with Passkey" : "Verify"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
