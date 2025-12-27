import { useState } from "react";
import { cn } from "@/lib/utils";

interface PathCellProps {
  path: string;
  className?: string;
  defaultMaxWidth?: string;
}

export function PathCell({
  path,
  className,
  // Default: mobile 200px, tablet XL, desktop 3XL
  defaultMaxWidth = "max-w-[200px] md:max-w-xl lg:max-w-3xl",
}: PathCellProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={cn(
        "cursor-pointer transition-all duration-200",
        isExpanded
          ? "break-all whitespace-normal"
          : `truncate ${defaultMaxWidth}`,
        className,
      )}
      onClick={(e) => {
        e.stopPropagation();
        setIsExpanded(!isExpanded);
      }}
      title={isExpanded ? "Click to collapse" : path}
    >
      {path}
    </div>
  );
}
