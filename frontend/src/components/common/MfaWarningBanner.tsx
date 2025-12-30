// frontend/src/components/common/MfaWarningBanner.tsx
/**
 * Persistent warning banner shown to admins who haven't enabled MFA.
 * Cannot be dismissed except by enabling MFA.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldAlert, X } from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { mfaApi } from "@/features/auth/api/mfa";
import { usersApi } from "@/features/users/api/users";
import { useAuthStore } from "@/store/authStore";

export function MfaWarningBanner() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);

  // Local state for immediate UI feedback or if user not loaded yet
  const [localDismissed, setLocalDismissed] = useState(false);
  const userId = user?.id;

  useEffect(() => {
    setLocalDismissed(false);
  }, [userId]);

  // Check MFA status only if we might need to show the banner
  const { data: mfaStatus } = useQuery({
    queryKey: ["mfa-status", userId],
    queryFn: mfaApi.getStatus,
    enabled: !!user && !localDismissed,
    refetchInterval: 60000, // Check every minute
  });

  const dismissMutation = useMutation({
    mutationFn: () => {
      const currentPrefs = user?.preferences || {};
      return usersApi.updateMe({
        preferences: { ...currentPrefs, mfa_banner_dismissed: true },
      });
    },
    onSuccess: (updatedUser) => {
      // Update local store with new user data (containing preferences)
      // Note: We need to cast or ensure updatedUser matches store User type
      if (user) {
        setUser({ ...user, ...updatedUser });
      }
    },
  });

  const handleDismiss = () => {
    setLocalDismissed(true);
    if (user) {
      dismissMutation.mutate();
    }
  };

  // Logic to determine visibility
  // 1. Must be logged in
  if (!user) return null;

  // 2. Must NOT have dismissed it (preferences take precedence)
  const isDismissed = user.preferences?.mfa_banner_dismissed || localDismissed;
  if (isDismissed) return null;

  // 3. MFA must NOT be enabled
  if (!mfaStatus || mfaStatus.mfa_enabled) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500/95 text-black px-4 py-3 shadow-lg">
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 flex-shrink-0" />
          <div>
            <span className="font-semibold">Security Notice:</span>{" "}
            <span>
              Enable Two-Factor Authentication to protect your account.
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/settings")}
            className="px-4 py-1.5 bg-black/20 hover:bg-black/30 rounded-lg font-medium transition-colors whitespace-nowrap"
          >
            Enable MFA Now
          </button>
          <button
            onClick={handleDismiss}
            className="p-1.5 hover:bg-black/10 rounded-full transition-colors"
            title="Dismiss"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
