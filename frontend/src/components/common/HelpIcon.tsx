import { useState } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface HelpIconProps {
  tooltip: string;
  className?: string;
}

/**
 * Reusable help icon with tooltip for providing contextual help.
 * Follows design spec: 16px circle with "?" inside, gray border.
 */
export function HelpIcon({ tooltip, className = "" }: HelpIconProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip open={isOpen} onOpenChange={setIsOpen}>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-[1.5px] border-gray-400 text-[11px] font-medium text-gray-500 hover:border-gray-600 hover:text-gray-700 dark:border-gray-500 dark:text-gray-400 dark:hover:border-gray-300 dark:hover:text-gray-200 transition-colors cursor-help ml-1 focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-1 ${className}`}
            aria-label="Help"
            onClick={(e) => {
              e.preventDefault();
              setIsOpen(!isOpen);
            }}
          >
            ?
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="top"
          className="max-w-[280px] text-sm bg-popover text-popover-foreground border border-border shadow-lg"
        >
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
