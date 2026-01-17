import { motion } from "framer-motion";
import { Download, Server, FileText, Subtitles } from "lucide-react";
import { HelpIcon } from "./HelpIcon";

interface FlowDiagramProps {
  isActive?: boolean;
}

/**
 * Visual webhook flow diagram showing:
 * qBittorrent → Webhook Script → API → Subtitle Download
 */
export function FlowDiagram({ isActive = true }: FlowDiagramProps) {
  const nodes = [
    {
      icon: Download,
      label: "qBittorrent",
      help: "Your torrent client triggers the webhook when a download completes",
      color: isActive ? "emerald" : "gray",
    },
    {
      icon: FileText,
      label: "Webhook Script",
      help: "A shell script that sends the download path to your API",
      color: isActive ? "blue" : "gray",
    },
    {
      icon: Server,
      label: "Subro API",
      help: "Your server processes the request and queues subtitle search",
      color: isActive ? "violet" : "gray",
    },
    {
      icon: Subtitles,
      label: "Subtitles",
      help: "Subtitles are automatically downloaded and placed with your media",
      color: isActive ? "amber" : "gray",
    },
  ];

  const colorClasses = {
    emerald: {
      bg: "bg-emerald-500/10 dark:bg-emerald-500/20",
      border: "border-emerald-500/30",
      icon: "text-emerald-500",
      line: "bg-emerald-500/50",
    },
    blue: {
      bg: "bg-blue-500/10 dark:bg-blue-500/20",
      border: "border-blue-500/30",
      icon: "text-blue-500",
      line: "bg-blue-500/50",
    },
    violet: {
      bg: "bg-violet-500/10 dark:bg-violet-500/20",
      border: "border-violet-500/30",
      icon: "text-violet-500",
      line: "bg-violet-500/50",
    },
    amber: {
      bg: "bg-amber-500/10 dark:bg-amber-500/20",
      border: "border-amber-500/30",
      icon: "text-amber-500",
      line: "bg-amber-500/50",
    },
    gray: {
      bg: "bg-gray-500/10 dark:bg-gray-500/20",
      border: "border-gray-500/30",
      icon: "text-gray-400",
      line: "bg-gray-400/50",
    },
  };

  return (
    <div className="w-full py-6">
      {/* Desktop: Horizontal layout */}
      <div className="hidden md:flex items-center justify-between gap-2">
        {nodes.map((node, index) => {
          const colors = colorClasses[node.color as keyof typeof colorClasses];
          const Icon = node.icon;

          return (
            <div key={node.label} className="flex items-center flex-1">
              {/* Node */}
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.15, duration: 0.3 }}
                className={`relative flex flex-col items-center p-4 rounded-xl border ${colors.bg} ${colors.border} min-w-[120px] group cursor-default`}
              >
                <div className={`p-3 rounded-full ${colors.bg} mb-2`}>
                  <Icon className={`h-6 w-6 ${colors.icon}`} />
                </div>
                <span className="text-sm font-medium text-foreground flex items-center gap-1">
                  {node.label}
                  <HelpIcon tooltip={node.help} />
                </span>
              </motion.div>

              {/* Connecting arrow */}
              {index < nodes.length - 1 && (
                <motion.div
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ delay: index * 0.15 + 0.2, duration: 0.3 }}
                  className="flex-1 flex items-center justify-center mx-2"
                >
                  <div className={`h-0.5 flex-1 ${colors.line} rounded-full`} />
                  <motion.div
                    animate={isActive ? { x: [0, 4, 0] } : {}}
                    transition={{
                      repeat: Infinity,
                      duration: 1.5,
                      delay: index * 0.3,
                    }}
                    className={`w-0 h-0 border-t-4 border-t-transparent border-b-4 border-b-transparent border-l-8 ${isActive ? "border-l-emerald-500" : "border-l-gray-400"} ml-1`}
                  />
                </motion.div>
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile: Vertical layout */}
      <div className="flex md:hidden flex-col items-center gap-4">
        {nodes.map((node, index) => {
          const colors = colorClasses[node.color as keyof typeof colorClasses];
          const Icon = node.icon;

          return (
            <div key={node.label} className="flex flex-col items-center">
              <motion.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                className={`flex items-center gap-3 p-3 rounded-xl border ${colors.bg} ${colors.border} w-full max-w-xs`}
              >
                <div className={`p-2 rounded-full ${colors.bg}`}>
                  <Icon className={`h-5 w-5 ${colors.icon}`} />
                </div>
                <span className="text-sm font-medium text-foreground flex items-center gap-1">
                  {node.label}
                  <HelpIcon tooltip={node.help} />
                </span>
              </motion.div>

              {index < nodes.length - 1 && (
                <motion.div
                  initial={{ scaleY: 0 }}
                  animate={{ scaleY: 1 }}
                  transition={{ delay: index * 0.1 + 0.1 }}
                  className="flex flex-col items-center h-6"
                >
                  <div className={`w-0.5 flex-1 ${colors.line}`} />
                  <div
                    className={`w-0 h-0 border-l-4 border-l-transparent border-r-4 border-r-transparent border-t-6 ${isActive ? "border-t-emerald-500" : "border-t-gray-400"}`}
                  />
                </motion.div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
