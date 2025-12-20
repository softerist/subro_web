import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { DashboardTile } from "./DashboardTile";
import { DashboardTile as TileType } from "../types";

interface SortableTileProps {
  tile: TileType;
  isEditable?: boolean;
  onEdit?: (tile: TileType) => void;
  onDelete?: (tile: TileType) => void;
}

export function SortableTile({
  tile,
  isEditable,
  onEdit,
  onDelete,
}: SortableTileProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: tile.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <DashboardTile
        tile={tile}
        isEditable={isEditable}
        onEdit={onEdit}
        onDelete={onDelete}
      />
    </div>
  );
}
