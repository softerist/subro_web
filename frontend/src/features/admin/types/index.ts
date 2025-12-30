export interface User {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  role: "admin" | "standard";
  created_at?: string; // Optional if not always present
}

export interface UserCreate {
  email: string;
  password: string;
  role?: "admin" | "standard";
  is_superuser?: boolean;
  is_active?: boolean;
}

export interface UserUpdate {
  email?: string;
  password?: string;
  role?: "admin" | "standard";
  is_superuser?: boolean;
  is_active?: boolean;
  mfa_enabled?: boolean;
  force_password_change?: boolean;
}
