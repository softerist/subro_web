import React from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  isLoading?: boolean;
  variant?: "default" | "destructive";
  // Position near triggering element
  targetRect?: {
    top: number;
    left: number;
    width: number;
    height: number;
  };
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  isLoading = false,
  variant = "default",
  targetRect,
}: ConfirmDialogProps) {
  const [isMobile, setIsMobile] = React.useState(false);

  // Track mobile state and handle resize
  React.useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 640);
    };

    // Initial check
    checkMobile();

    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  const hasPosition = targetRect !== undefined && !isMobile;

  // Calculate position - appear below the triggering element, anchored to the right
  const getDialogStyle = (): React.CSSProperties => {
    if (!hasPosition || !targetRect) {
      return {}; // Center fallback
    }

    const dialogWidth = 260; // max-w-[260px]
    const dialogHeight = 150; // approximate height after slimming down
    const margin = 8;
    const viewportPadding = 16;

    // Position: Right edge of dialog aligns with right edge of target
    let left = targetRect.left + targetRect.width - dialogWidth;

    // Vertical Positioning: below target
    let top = targetRect.top + targetRect.height + margin;

    // Boundary Checks

    // If dialog would go off left edge, shift it right
    if (left < viewportPadding) {
      left = viewportPadding;
    }

    // If dialog would go off right edge, shift it left
    if (left + dialogWidth > window.innerWidth - viewportPadding) {
      left = window.innerWidth - dialogWidth - viewportPadding;
    }

    // If dialog would go below viewport, position it above the target
    if (top + dialogHeight > window.innerHeight - viewportPadding) {
      top = targetRect.top - dialogHeight - margin;
    }

    // Clamp vertical position safely
    top = Math.max(
      viewportPadding,
      Math.min(top, window.innerHeight - dialogHeight - viewportPadding),
    );

    return {
      position: "fixed" as const,
      top: `${top}px`,
      left: `${left}px`,
    };
  };

  const dialogStyle = getDialogStyle();

  return createPortal(
    <AnimatePresence>
      {open && (
        <div
          className={`fixed inset-0 z-[9999] ${hasPosition ? "" : "flex items-center justify-center p-4 sm:p-6"}`}
        >
          {/* Backdrop with advanced blur */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => !isLoading && onOpenChange(false)}
            className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm cursor-pointer"
          />

          {/* Modal Container - Compact Design */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{
              opacity: 1,
              scale: 1,
              y: 0,
              transition: {
                type: "spring",
                damping: 25,
                stiffness: 350,
              },
            }}
            exit={{
              opacity: 0,
              scale: 0.95,
              y: 8,
              transition: { duration: 0.15, ease: "easeIn" },
            }}
            style={dialogStyle}
            className={`${hasPosition ? "" : "relative"} w-full max-w-[260px] overflow-hidden rounded-xl border border-white/10 bg-slate-900/95 p-3 shadow-2xl backdrop-blur-2xl sm:p-3 z-[10000]`}
          >
            {/* Glossy Overlay */}
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-b from-white/5 to-transparent" />

            {/* Content Space */}
            <div className="relative z-10">
              <div className="flex items-start gap-3 mb-2">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg shadow-lg ${
                    variant === "destructive"
                      ? "bg-red-500/10 text-red-400 ring-1 ring-red-500/20 shadow-red-500/10"
                      : "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20 shadow-blue-500/10"
                  }`}
                >
                  <AlertTriangle className="h-3.5 w-3.5" />
                </div>

                <div className="flex-1 pt-0.5">
                  <h3 className="text-sm font-bold text-white tracking-tight mb-0.5">
                    {title}
                  </h3>
                  <div className="text-slate-400 text-[11px] leading-relaxed">
                    {description}
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 mt-3">
                <Button
                  variant="ghost"
                  onClick={() => onOpenChange(false)}
                  disabled={isLoading}
                  className="h-8 px-3 rounded-lg text-xs text-slate-400 hover:text-white hover:bg-white/5 transition-all"
                >
                  {cancelLabel}
                </Button>
                <Button
                  onClick={onConfirm}
                  disabled={isLoading}
                  variant={
                    variant === "destructive" ? "destructive" : "default"
                  }
                  className={`h-8 px-4 rounded-lg text-xs font-bold transition-all active:scale-[0.98] shadow-lg ${
                    variant === "destructive"
                      ? "bg-red-500 hover:bg-red-400 shadow-red-500/20"
                      : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-blue-500/20"
                  }`}
                >
                  {isLoading ? (
                    <div className="flex items-center gap-1.5">
                      <div className="h-3 w-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>...</span>
                    </div>
                  ) : (
                    confirmLabel
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
