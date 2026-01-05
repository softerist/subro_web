export interface Job {
  id: string;
  status:
    | "PENDING"
    | "RUNNING"
    | "SUCCEEDED"
    | "FAILED"
    | "CANCELLED"
    | "CANCELLING";
  folder_path: string;
  language: string | null;
  submitted_at: string;
  started_at: string | null;
  completed_at: string | null;
  celery_task_id: string | null;
  exit_code: number | null;
  result_message: string | null;
  log_snippet: string | null;
  error_message?: string;
}

export interface JobCreate {
  folder_path: string;
  language?: string;
  log_level?: "DEBUG" | "INFO" | "WARNING" | "ERROR";
}

export interface LogMessage {
  type: "log" | "status" | "info" | "system" | "error";
  payload: {
    ts?: string;
    stream?: "stdout" | "stderr";
    message?: string;
    status?: string;
    job_id?: string;
    exit_code?: number;
    error_message?: string;
    [key: string]: unknown;
  };
}

export interface StoragePath {
  id: string;
  path: string;
  label?: string;
  created_at: string;
  updated_at: string;
}

export interface StoragePathCreate {
  path: string;
  label?: string;
}
