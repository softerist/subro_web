import React from "react";

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
  positionY?: number;
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
  positionY,
}: ConfirmDialogProps) {
  if (!open) return null;

  // Calculate position - similar to Save bar logic
  const computedTop = positionY
    ? `${Math.min(Math.max(positionY + 60, 150), window.innerHeight - 200)}px`
    : "50%";

  const translateY = positionY ? "0" : "-50%";

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-[1px] z-[200] animate-in fade-in duration-300"
        onClick={() => !isLoading && onOpenChange(false)}
      />

      {/* Floating Dialog - positioned near clicked button */}
      <div
        className="fixed left-1/2 -translate-x-1/2 z-[201] animate-in fade-in slide-in-from-bottom-4 duration-200"
        style={{
          top: computedTop,
          transform: `translateX(-50%) translateY(${translateY})`,
        }}
      >
        <div className="bg-slate-800/95 backdrop-blur-md border border-slate-600 rounded-2xl shadow-2xl shadow-black/40 px-6 py-4 flex flex-col gap-4 min-w-[320px] max-w-md">
          {/* Header */}
          <div className="flex items-center gap-3">
            <div
              className={`h-2 w-2 rounded-full ${
                variant === "destructive"
                  ? "bg-red-500 animate-pulse"
                  : "bg-amber-500 animate-pulse"
              }`}
            />
            <span className="text-white text-sm font-semibold">{title}</span>
          </div>

          {/* Description */}
          <div className="text-slate-400 text-sm pl-5">{description}</div>

          {/* Divider + Buttons */}
          <div className="flex items-center gap-4 pt-2 border-t border-slate-700">
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
              className="px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors disabled:opacity-50"
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={isLoading}
              className={`px-4 py-1.5 text-white text-sm font-medium rounded-lg transition-all shadow-lg disabled:opacity-50 ${
                variant === "destructive"
                  ? "bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 shadow-red-500/20 hover:shadow-red-500/40"
                  : "bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 shadow-blue-500/20 hover:shadow-blue-500/40"
              }`}
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Processing...
                </span>
              ) : (
                confirmLabel
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
