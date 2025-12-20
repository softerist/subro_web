import { useState, useEffect } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import { Loader2, Plus } from "lucide-react";

import { useDashboard } from "../hooks/useDashboard";
import { SortableTile } from "./SortableTile";
import { DashboardTile } from "./DashboardTile";
import {
  TileEditorDialog,
  DashboardTile as DashboardTileType,
} from "./TileEditorDialog";
import { Card, CardContent } from "@/components/ui/card";

interface TileGridProps {
  isEditable?: boolean;
}

export function TileGrid({ isEditable = false }: TileGridProps) {
  const { tiles, isLoading, reorderTiles, createTile, updateTile, deleteTile } =
    useDashboard(isEditable);
  const [localTiles, setLocalTiles] = useState(tiles);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingTile, setEditingTile] = useState<DashboardTileType | undefined>(
    undefined,
  );

  // Sync local state with fetched data
  useEffect(() => {
    if (tiles) {
      setLocalTiles(tiles);
    }
  }, [tiles]);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setLocalTiles((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id);
        const newIndex = items.findIndex((item) => item.id === over.id);
        const newOrder = arrayMove(items, oldIndex, newIndex);

        // Trigger API update
        reorderTiles({ ordered_ids: newOrder.map((t) => t.id) });

        return newOrder;
      });
    }
  }

  const handleCreate = () => {
    setEditingTile(undefined);
    setIsDialogOpen(true);
  };

  const handleEdit = (tile: DashboardTileType) => {
    setEditingTile(tile);
    setIsDialogOpen(true);
  };

  const handleDelete = async (tile: DashboardTileType) => {
    if (confirm(`Are you sure you want to delete "${tile.title}"?`)) {
      if (tile.id) {
        await deleteTile(tile.id);
      }
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleSave = async (data: any) => {
    if (editingTile?.id) {
      await updateTile({ id: editingTile.id, data });
    } else {
      await createTile(data);
    }
  };

  if (isLoading && !localTiles?.length) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  /*
    if (!localTiles?.length && !isEditable) {
        return (
            <div className="text-center text-muted-foreground py-10">
                No tiles available.
            </div>
        );
    }
    */

  return (
    <>
      {isEditable ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={localTiles.map((t) => t.id)}
            strategy={rectSortingStrategy}
          >
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 p-4">
              {localTiles.map((tile) => (
                <SortableTile
                  key={tile.id}
                  tile={tile}
                  isEditable={isEditable}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                />
              ))}
              {/* Add New Tile Button (in grid) */}
              <Card
                className="flex items-center justify-center h-full border-dashed cursor-pointer hover:border-primary/50 transition-colors min-h-[100px]"
                onClick={handleCreate}
              >
                <CardContent className="flex flex-col items-center justify-center p-6 text-muted-foreground">
                  <Plus className="h-8 w-8 mb-2" />
                  <span className="text-sm font-medium">Add Tile</span>
                </CardContent>
              </Card>
            </div>
          </SortableContext>
        </DndContext>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 p-4">
          {!localTiles?.length ? (
            <div className="col-span-full text-center text-muted-foreground py-8">
              No tiles available.
            </div>
          ) : (
            localTiles.map((tile) => (
              <DashboardTile key={tile.id} tile={tile} />
            ))
          )}
        </div>
      )}

      <TileEditorDialog
        open={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onSave={handleSave}
        initialData={editingTile}
      />
    </>
  );
}
