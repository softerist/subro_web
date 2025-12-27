import {
  ExternalLink,
  FileText,
  Globe,
  LayoutGrid,
  Edit,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DashboardTile as DashboardTileType } from "../types";

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
    <Wrapper
      {...wrapperProps}
      className="block h-full group relative transition-transform hover:scale-[1.02] active:scale-[0.98]"
      onClick={onClick}
    >
      <Card className="h-full cursor-pointer hover:border-primary/50 overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 p-3 pb-2 gap-2">
          <CardTitle
            className="text-sm font-medium truncate flex-1"
            title={tile.title}
          >
            {tile.title}
            {!tile.is_active && isEditable && (
              <span className="ml-1 text-[10px] text-slate-500 font-normal">
                (Hidden)
              </span>
            )}
          </CardTitle>

          {isEditable ? (
            <div className="flex items-center space-x-1 shrink-0 bg-slate-800/80 rounded-md p-0.5 border border-slate-700/50">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 hover:bg-slate-700 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit?.(tile);
                }}
                title="Edit Tile"
              >
                <Edit className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete?.(tile);
                }}
                title="Delete Tile"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ) : (
            <IconComponent className="h-4 w-4 text-slate-400 shrink-0" />
          )}
        </CardHeader>
        <CardContent className="p-3 pt-0">
          <div
            className="text-xs text-slate-400 truncate opacity-70"
            title={tile.url}
          >
            {tile.url}
          </div>
        </CardContent>
      </Card>
    </Wrapper>
  );
}
