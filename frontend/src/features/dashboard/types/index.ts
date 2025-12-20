export interface DashboardTile {
  id: string;
  title: string;
  url: string;
  icon: string;
  order_index: number;
  is_active: boolean;
}

export interface DashboardTileCreate {
  title: string;
  url: string;
  icon?: string;
  is_active?: boolean;
}

export interface DashboardTileUpdate {
  title?: string;
  url?: string;
  icon?: string;
  order_index?: number;
  is_active?: boolean;
}

export interface ReorderPayload {
  ordered_ids: string[];
}
