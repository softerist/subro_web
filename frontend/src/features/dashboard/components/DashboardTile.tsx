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
      <Card className="h-full cursor-pointer hover:border-primary/50 relative">
        {isEditable && (
          <div className="absolute top-2 right-2 flex space-x-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900/80 rounded-md p-1 z-10">
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(e) => {
                e.stopPropagation();
                onEdit?.(tile);
              }}
            >
              <Edit className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                onDelete?.(tile);
              }}
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        )}
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">
            {tile.title}{" "}
            {!tile.is_active && isEditable && (
              <span className="text-xs text-slate-400">(Hidden)</span>
            )}
          </CardTitle>
          <IconComponent className="h-4 w-4 text-slate-400" />
        </CardHeader>
        <CardContent>
          <div className="text-xs text-slate-400 truncate">{tile.url}</div>
        </CardContent>
      </Card>
    </Wrapper>
  );
}
