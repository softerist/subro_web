import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Save, Loader2, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SavePillProps {
  isVisible: boolean;
  isLoading: boolean;
  hasChanges: boolean;
  onSave: () => void;
  onDiscard: () => void;
  message?: string;
  isSuccess?: boolean;
  // Container rect for dynamic centering
  containerRef?: React.RefObject<HTMLElement>;
}

export function SavePill({
  isVisible,
  isLoading,
  hasChanges,
  onSave,
  onDiscard,
  message = "Unsaved Changes",
  isSuccess = false,
  containerRef,
}: SavePillProps) {
  // Calculate center position based on container
  const getPositionStyle = (): React.CSSProperties => {
    if (containerRef?.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      return {
        left: `${centerX}px`,
        transform: "translateX(-50%)",
      };
    }
    // Fallback: center in content area (after 230px sidebar)
    return {
      left: "calc(230px + (100vw - 230px) / 2)",
      transform: "translateX(-50%)",
    };
  };

  const content = (
    <AnimatePresence>
      {(isVisible || isSuccess) && (
        <div
          className="fixed bottom-6 z-[9999] pointer-events-none"
          style={getPositionStyle()}
        >
          <motion.div
            initial={{ y: 20, opacity: 0, scale: 0.95 }}
            animate={{
              y: 0,
              opacity: 1,
              scale: 1,
              transition: {
                type: "spring",
                damping: 25,
                stiffness: 350,
              },
            }}
            exit={{
              y: 20,
              opacity: 0,
              scale: 0.95,
              transition: { duration: 0.2, ease: "easeIn" },
            }}
            className="pointer-events-auto"
          >
            <div
              className={`relative flex items-center gap-3 px-4 py-2.5 rounded-xl border shadow-lg backdrop-blur-xl transition-all duration-300 ${
                isSuccess
                  ? "bg-emerald-500/20 border-emerald-500/30 text-emerald-400"
                  : "bg-slate-900/90 border-white/10 text-white"
              }`}
            >
              {/* Glossy shine */}
              <div className="absolute inset-0 rounded-xl bg-gradient-to-t from-white/[0.02] to-white/[0.05] pointer-events-none" />

              <div className="flex items-center gap-2">
                {isSuccess ? (
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-slate-950"
                  >
                    <CheckCircle className="h-3 w-3" />
                  </motion.div>
                ) : isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
                ) : (
                  <div className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-500 text-white shadow-md shadow-blue-500/20 pulse-subtle">
                    <Save className="h-3 w-3" />
                  </div>
                )}

                <span className="text-xs font-semibold tracking-tight whitespace-nowrap">
                  {isSuccess ? "Saved!" : message}
                </span>
              </div>

              {!isSuccess && hasChanges && !isLoading && (
                <div className="flex items-center gap-1.5 pl-3 border-l border-white/10">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onDiscard}
                    className="h-6 px-2 rounded-md text-[10px] text-slate-400 hover:text-white hover:bg-white/5"
                  >
                    Discard
                  </Button>
                  <Button
                    size="sm"
                    onClick={onSave}
                    className="h-6 px-3 rounded-md text-[10px] font-bold bg-white text-slate-950 hover:bg-slate-200 transition-all shadow-md"
                  >
                    Save
                  </Button>
                </div>
              )}

              {!isSuccess && isLoading && (
                <span className="pl-3 border-l border-white/10 text-[10px] text-slate-500 animate-pulse">
                  Saving...
                </span>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );

  // Use portal to render directly to body, escaping any scrollable containers
  return createPortal(content, document.body);
}
