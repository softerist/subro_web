import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { dashboardApi } from "../api/dashboard";
import {
  DashboardTileCreate,
  DashboardTileUpdate,
  ReorderPayload,
} from "../types";

export function useDashboard(isAdmin: boolean = false) {
  const queryClient = useQueryClient();
  const queryKey = ["dashboard-tiles", isAdmin ? "admin" : "public"];

  const {
    data: tiles,
    isLoading,
    error,
  } = useQuery({
    queryKey,
    queryFn: isAdmin ? dashboardApi.getAll : dashboardApi.getActive,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  const reorderMutation = useMutation({
    mutationFn: (payload: ReorderPayload) => dashboardApi.reorder(payload),
    onSuccess: (newTiles) => {
      // Optimistically update or just invalidate. Given we return newTiles, setQueryData is fine for current view,
      // but we should also invalidate the other view if possible, or just invalidate all for consistency.
      // Setting data is faster for the current view.
      queryClient.setQueryData(queryKey, newTiles);
      // Also invalidate the other view so it picks up the new order next time
      queryClient.invalidateQueries({ queryKey: ["dashboard-tiles"] });
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: DashboardTileCreate) => dashboardApi.create(data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["dashboard-tiles"] }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: DashboardTileUpdate }) =>
      dashboardApi.update(id, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["dashboard-tiles"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => dashboardApi.delete(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["dashboard-tiles"] }),
  });

  return {
    tiles: tiles || [],
    isLoading,
    error,
    reorderTiles: reorderMutation.mutate,
    createTile: createMutation.mutateAsync,
    updateTile: updateMutation.mutateAsync,
    deleteTile: deleteMutation.mutateAsync,
    isReordering: reorderMutation.isPending,
  };
}
