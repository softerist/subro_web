// frontend/src/components/common/MfaWarningBanner.tsx
/**
 * Persistent warning banner shown to admins who haven't enabled MFA.
 * Cannot be dismissed except by enabling MFA.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { mfaApi } from "@/features/auth/api/mfa";

export function MfaWarningBanner() {
  const navigate = useNavigate();
  const [show, setShow] = useState(false);

  // Check if MFA setup is required from localStorage
  useEffect(() => {
    const required = localStorage.getItem("mfa_setup_required");
    setShow(required === "true");
  }, []);

  // Check MFA status - if enabled, clear the warning
  const { data: mfaStatus } = useQuery({
    queryKey: ["mfa-status"],
    queryFn: mfaApi.getStatus,
    enabled: show,
    refetchInterval: 5000, // Check every 5 seconds
  });

  useEffect(() => {
    if (mfaStatus?.mfa_enabled) {
      localStorage.removeItem("mfa_setup_required");
      setShow(false);
    }
  }, [mfaStatus]);

  if (!show) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500/95 text-black px-4 py-3 shadow-lg">
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 flex-shrink-0" />
          <div>
            <span className="font-semibold">Security Notice:</span>{" "}
            <span>
              Administrator accounts require Two-Factor Authentication.
            </span>
          </div>
        </div>
        <button
          onClick={() => navigate("/settings")}
          className="px-4 py-1.5 bg-black/20 hover:bg-black/30 rounded-lg font-medium transition-colors whitespace-nowrap"
        >
          Enable MFA Now
        </button>
      </div>
    </div>
  );
}
