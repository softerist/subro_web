import { useState } from "react";
import { ShieldCheck, ShieldAlert, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { verifyAuditIntegrity } from "../api/audit";

export function VerifyIntegrityDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [result, setResult] = useState<{
    verified: boolean;
    issues: string[];
  } | null>(null);

  const handleVerify = async () => {
    setIsVerifying(true);
    setResult(null);
    try {
      const response = await verifyAuditIntegrity();
      setResult(response);
      if (response.verified) {
        toast.success("Audit log integrity verified successfully!");
      } else {
        toast.error("Audit log integrity check failed!");
      }
    } catch (error) {
      toast.error("Failed to perform integrity check. Please try again.");
      console.error(error);
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <ShieldCheck className="mr-2 h-4 w-4" />
          Verify Integrity
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Audit Log Integrity Verification</DialogTitle>
          <DialogDescription>
            This will scan the audit log hash chains to detect any tampering or
            inconsistencies.
          </DialogDescription>
        </DialogHeader>

        <div className="py-6 min-h-[120px] flex flex-col items-center justify-center">
          {isVerifying ? (
            <div className="flex flex-col items-center space-y-4 text-center">
              <RefreshCw className="h-10 w-10 text-primary animate-spin" />
              <p className="text-sm text-muted-foreground animate-pulse">
                Hashing event chains...
              </p>
            </div>
          ) : result ? (
            <div className="w-full space-y-4">
              {result.verified ? (
                <Alert className="border-emerald-500/50 bg-emerald-500/10">
                  <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  <AlertTitle className="text-emerald-500">Verified</AlertTitle>
                  <AlertDescription className="text-emerald-500/90">
                    The audit log chain is intact. No tampering detected.
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant="destructive">
                  <ShieldAlert className="h-4 w-4" />
                  <AlertTitle>Integrity Breach</AlertTitle>
                  <AlertDescription>
                    Detected {result.issues.length} potential inconsistencies in
                    the hash chain.
                  </AlertDescription>
                </Alert>
              )}

              {result.issues.length > 0 && (
                <div className="mt-4 p-3 bg-muted rounded-md max-h-[150px] overflow-auto">
                  <p className="text-xs font-semibold mb-2 uppercase text-muted-foreground">
                    Found Issues
                  </p>
                  <ul className="list-disc list-inside space-y-1">
                    {result.issues.map((issue, i) => (
                      <li key={i} className="text-xs text-destructive/90">
                        {issue}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center space-y-4 opacity-40">
              <ShieldCheck className="h-12 w-12" />
              <p className="text-sm">Ready to scan logs</p>
            </div>
          )}
        </div>

        <DialogFooter className="sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setResult(null);
              setIsOpen(false);
            }}
          >
            Close
          </Button>
          <Button onClick={handleVerify} disabled={isVerifying}>
            {isVerifying
              ? "Verifying..."
              : result
                ? "Re-verify"
                : "Start Verification"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
