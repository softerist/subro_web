// frontend/src/features/auth/components/PasskeySettings.tsx
/**
 * Passkey Settings Component
 *
 * Allows users to register, view, rename, and delete passkeys.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Key,
  Plus,
  Loader2,
  Trash2,
  Pencil,
  Check,
  X,
  Smartphone,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
} from "@/components/ui/dialog";
import { useAuthStore } from "@/store/authStore";
import { passkeyApi, isWebAuthnSupported, PasskeyInfo } from "../api/passkey";

export function PasskeySettings() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.user?.id);

  const [showRegisterDialog, setShowRegisterDialog] = useState(false);
  const [deviceName, setDeviceName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Check if WebAuthn is supported
  const webAuthnSupported = isWebAuthnSupported();

  // Fetch passkeys
  const { data: passkeyStatus, isLoading } = useQuery({
    queryKey: ["passkeys", userId],
    queryFn: passkeyApi.listPasskeys,
    enabled: webAuthnSupported,
  });

  // Register mutation
  const registerMutation = useMutation({
    mutationFn: (name: string) => passkeyApi.register(name),
    onSuccess: () => {
      setShowRegisterDialog(false);
      setDeviceName("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["passkeys", userId] });
    },
    onError: (err: unknown) => {
      const errorMessage = (
        err as { response?: { data?: { detail?: string } }; message?: string }
      )?.response?.data?.detail ||
        (err as Error)?.message ||
        "Failed to register passkey";
      setError(errorMessage);
    },
  });

  // Rename mutation
  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      passkeyApi.renamePasskey(id, name),
    onSuccess: () => {
      setEditingId(null);
      setEditName("");
      queryClient.invalidateQueries({ queryKey: ["passkeys", userId] });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: passkeyApi.deletePasskey,
    onSuccess: () => {
      setDeleteConfirmId(null);
      queryClient.invalidateQueries({ queryKey: ["passkeys", userId] });
    },
  });

  const handleRegister = () => {
    setError(null);
    registerMutation.mutate(deviceName || "Passkey");
  };

  const handleStartEdit = (passkey: PasskeyInfo) => {
    setEditingId(passkey.id);
    setEditName(passkey.device_name || "");
  };

  const handleSaveEdit = (id: string) => {
    if (editName.trim()) {
      renameMutation.mutate({ id, name: editName.trim() });
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditName("");
  };

  // WebAuthn not supported
  if (!webAuthnSupported) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5 text-muted-foreground" />
            Passkeys
          </CardTitle>
          <CardDescription>
            Passwordless authentication with biometrics or security keys
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="p-4 bg-muted/50 border rounded-lg">
            <p className="text-sm text-muted-foreground">
              Your browser doesn't support passkeys. Please use a modern browser
              like Chrome, Safari, Firefox, or Edge.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-6 w-6 animate-spin" role="progressbar" />
      </div>
    );
  }

  const passkeys = passkeyStatus?.passkeys || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Key className="h-5 w-5" />
          Passkeys
        </CardTitle>
        <CardDescription>
          Sign in with your fingerprint, face, or security key — no password needed
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Info Banner */}
        {passkeys.length === 0 && (
          <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
            <div className="flex items-start gap-3">
              <ShieldCheck className="h-5 w-5 text-primary mt-0.5" />
              <div className="text-sm">
                <p className="font-medium">Enable passwordless login</p>
                <p className="text-muted-foreground mt-1">
                  Passkeys are more secure than passwords and let you sign in
                  with Touch ID, Face ID, Windows Hello, or a security key.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Passkey List */}
        {passkeys.length > 0 && (
          <div className="space-y-2">
            {passkeys.map((passkey) => (
              <div
                key={passkey.id}
                className="flex items-center justify-between p-3 border rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <Smartphone className="h-5 w-5 text-muted-foreground" />
                  <div>
                    {editingId === passkey.id ? (
                      <div className="flex items-center gap-2">
                        <Input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="h-8 w-48"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveEdit(passkey.id);
                            if (e.key === "Escape") handleCancelEdit();
                          }}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleSaveEdit(passkey.id)}
                          disabled={renameMutation.isPending}
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleCancelEdit}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <>
                        <p className="font-medium">
                          {passkey.device_name || "Passkey"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Added{" "}
                          {passkey.created_at
                            ? new Date(passkey.created_at).toLocaleDateString()
                            : "Unknown"}
                          {passkey.last_used_at && (
                            <>
                              {" • Last used "}
                              {new Date(passkey.last_used_at).toLocaleDateString()}
                            </>
                          )}
                          {passkey.backup_state && " • Synced"}
                        </p>
                      </>
                    )}
                  </div>
                </div>
                {editingId !== passkey.id && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleStartEdit(passkey)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteConfirmId(passkey.id)}
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Add Passkey Button */}
        <Button
          onClick={() => setShowRegisterDialog(true)}
          className="w-full"
          variant={passkeys.length > 0 ? "outline" : "default"}
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Passkey
        </Button>

        {/* Register Dialog */}
        <Dialog open={showRegisterDialog} onOpenChange={setShowRegisterDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add a Passkey</DialogTitle>
              <DialogDescription>
                Your browser will prompt you to authenticate with biometrics or
                a security key.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Device Name (optional)
                </label>
                <Input
                  value={deviceName}
                  onChange={(e) => setDeviceName(e.target.value)}
                  placeholder="e.g., MacBook Pro Touch ID"
                />
                <p className="text-xs text-muted-foreground">
                  A friendly name to identify this passkey
                </p>
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setShowRegisterDialog(false);
                  setDeviceName("");
                  setError(null);
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={handleRegister}
                disabled={registerMutation.isPending}
              >
                {registerMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Continue
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete Confirmation Dialog */}
        <Dialog
          open={deleteConfirmId !== null}
          onOpenChange={(open) => !open && setDeleteConfirmId(null)}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete Passkey?</DialogTitle>
              <DialogDescription>
                This passkey will be removed from your account. You can always
                add it again later.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={() => deleteConfirmId && deleteMutation.mutate(deleteConfirmId)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Delete
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
