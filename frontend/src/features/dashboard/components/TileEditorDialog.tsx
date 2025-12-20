import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { DashboardTileCreate, DashboardTileUpdate } from "../types";

export interface DashboardTile extends DashboardTileCreate {
  id?: string;
  order_index?: number;
}

interface TileEditorDialogProps {
  open: boolean;
  initialData?: DashboardTile;
  onClose: () => void;
  onSave: (data: DashboardTileCreate | DashboardTileUpdate) => Promise<void>;
}

export function TileEditorDialog({
  open,
  initialData,
  onClose,
  onSave,
}: TileEditorDialogProps) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [icon, setIcon] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTitle(initialData?.title || "");
      setUrl(initialData?.url || "");
      setIcon(initialData?.icon || "");
      setIsActive(initialData?.is_active ?? true);
      setError(null);
    }
  }, [open, initialData]);

  const handleSave = async () => {
    if (!title.trim() || !url.trim()) {
      setError("Title and URL are required.");
      return;
    }

    try {
      setIsSaving(true);
      await onSave({
        title,
        url,
        icon,
        is_active: isActive,
      });
      onClose();
    } catch (e) {
      setError("Failed to save tile.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{initialData ? "Edit Tile" : "New Tile"}</DialogTitle>
          <DialogDescription>
            {initialData
              ? "Update the details of the dashboard tile."
              : "Create a new tile for the dashboard."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {error && <div className="text-destructive text-sm">{error}</div>}
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="title" className="text-right">
              Title
            </Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="col-span-3"
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="url" className="text-right">
              URL
            </Label>
            <Input
              id="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="col-span-3"
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="icon" className="text-right">
              Icon
            </Label>
            <Input
              id="icon"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              className="col-span-3"
              placeholder="e.g. globe (optional)"
            />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="active" className="text-right">
              Active
            </Label>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="active"
                checked={isActive}
                onCheckedChange={(checked) => setIsActive(!!checked)}
              />
              <label
                htmlFor="active"
                className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
              >
                Visible to users
              </label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSaving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
