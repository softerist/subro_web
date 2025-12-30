import {
  ExternalLink,
  FileText,
  Globe,
  LayoutGrid,
  Edit,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { DashboardTile as DashboardTileType } from "../types";
import { cn } from "@/lib/utils";

// Simple mapping for demonstration
const IconMap: Record<string, React.ElementType> = {
  default: FileText,
  globe: Globe,
  grid: LayoutGrid,
  link: ExternalLink,
};

interface DashboardTileProps {
  tile: DashboardTileType;
  onClick?: () => void;
  isEditable?: boolean;
  onEdit?: (tile: DashboardTileType) => void;
  onDelete?: (tile: DashboardTileType) => void;
}

export function DashboardTile({
  tile,
  onClick,
  isEditable,
  onEdit,
  onDelete,
}: DashboardTileProps) {
  // Dynamic icon lookup
  const IconComponent = IconMap[tile.icon?.toLowerCase()] || IconMap.default;

  const Wrapper = isEditable ? "div" : "a";
  const wrapperProps = isEditable
    ? {}
    : {
        href: tile.url,
        target: "_blank",
        rel: "noopener noreferrer",
      };

  return (
    <Wrapper {...wrapperProps} className="block h-full group" onClick={onClick}>
      <div
        className={cn(
          "quick-tile h-full relative",
          !tile.is_active && isEditable && "opacity-60",
        )}
      >
        {/* Icon Container */}
        <div className="quick-tile-icon">
          <IconComponent className="h-4 w-4 text-white" />
        </div>

        {/* Title */}
        <span className="quick-tile-title truncate w-full" title={tile.title}>
          {tile.title}
          {!tile.is_active && isEditable && (
            <span className="ml-1 text-[10px] text-muted-foreground font-normal">
              (Hidden)
            </span>
          )}
        </span>

        {/* URL subtitle */}
        <span
          className="text-[11px] text-muted-foreground truncate w-full opacity-60"
          title={tile.url}
        >
          {tile.url?.replace(/^https?:\/\//, "").split("/")[0]}
        </span>

        {/* Edit Controls */}
        {isEditable && (
          <div className="absolute top-2 right-2 flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity bg-card/90 backdrop-blur-sm rounded-md p-0.5 border border-border shadow-sm">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 hover:bg-secondary transition-colors"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                onEdit?.(tile);
              }}
              title="Edit Tile"
              aria-label="Edit tile"
            >
              <Edit className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive hover:text-destructive hover:bg-destructive/10 transition-colors"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
                onDelete?.(tile);
              }}
              title="Delete Tile"
              aria-label="Delete tile"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>
    </Wrapper>
  );
}
