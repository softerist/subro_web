import { useState } from "react";
import { cn } from "@/lib/utils";

interface PathCellProps {
  path: string;
  className?: string;
  defaultMaxWidth?: string;
  /** Controlled mode: if provided, component uses this instead of internal state */
  isExpanded?: boolean;
  /** Controlled mode: callback when expansion should toggle */
  onToggle?: () => void;
}

export function PathCell({
  path,
  className,
  // Default: mobile 200px, tablet XL, desktop 3XL
  defaultMaxWidth = "max-w-[200px] md:max-w-xl lg:max-w-3xl",
  isExpanded: controlledExpanded,
  onToggle,
}: PathCellProps) {
  const [internalExpanded, setInternalExpanded] = useState(false);

  // Use controlled mode if isExpanded prop is provided
  const isControlled = controlledExpanded !== undefined;
  const isExpanded = isControlled ? controlledExpanded : internalExpanded;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isControlled && onToggle) {
      onToggle();
    } else {
      setInternalExpanded(!internalExpanded);
    }
  };

  return (
    <div
      className={cn(
        "cursor-pointer transition-all duration-200",
        isExpanded
          ? "break-all whitespace-normal"
          : `truncate ${defaultMaxWidth}`,
        className,
      )}
      onClick={handleClick}
      title={isExpanded ? "Click to collapse" : path}
    >
      {path}
    </div>
  );
}
