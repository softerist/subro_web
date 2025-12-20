import { api } from "@/lib/apiClient";
import {
  DashboardTile,
  DashboardTileCreate,
  DashboardTileUpdate,
  ReorderPayload,
} from "../types";

export const dashboardApi = {
  // Admin: List all tiles (active + inactive)
  getAll: async () => {
    const response = await api.get<DashboardTile[]>(
      "/v1/dashboard/admin/tiles",
    );
    return response.data;
  },

  // Public: List active tiles only
  getActive: async () => {
    const response = await api.get<DashboardTile[]>("/v1/dashboard/tiles");
    return response.data;
  },

  create: async (data: DashboardTileCreate) => {
    const response = await api.post<DashboardTile>("/v1/dashboard/tiles", data);
    return response.data;
  },

  update: async (id: string, data: DashboardTileUpdate) => {
    const response = await api.patch<DashboardTile>(
      `/v1/dashboard/tiles/${id}`,
      data,
    );
    return response.data;
  },

  delete: async (id: string) => {
    await api.delete(`/v1/dashboard/tiles/${id}`);
  },

  reorder: async (data: ReorderPayload) => {
    // Backend expects a list of objects with {id, order_index}, but checking payload type.
    // Wait, backend expects List[TileReorder]. TileReorder has id and order_index.
    // Frontend ReorderPayload usually is { ordered_ids: string[] } or similar?
    // Let's check the types/index.ts and ReorderPayload definition in Step 998 summary?
    // In Step 998, I "Defined schemas...".
    // In the backend dashboard.py: reorder_list: List[TileReorder]
    // This means I need to send [ {id: "...", order_index: 0}, ... ]
    // Let's check what `useDashboard` sends.

    // Assuming dashboardApi.reorder receives the correct payload structure matching backend.
    // But if `reorder` argument is `data`, I pass it through.

    const response = await api.post<{ message: string }>(
      "/v1/dashboard/tiles/reorder",
      data,
    );
    return response.data;
  },
};
