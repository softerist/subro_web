export interface StoragePath {
  id: string;
  path: string;
  label?: string;
  created_at: string;
}

export interface StoragePathCreate {
  path: string;
  label?: string;
}
