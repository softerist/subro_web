export interface UserPreferences {
  mfa_banner_dismissed?: boolean;
  [key: string]: unknown;
}

export interface User {
  id: string;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  role: "admin" | "standard";
  created_at?: string;
  updated_at?: string;
  preferences?: UserPreferences;
  force_password_change?: boolean;
  mfa_enabled?: boolean;
}

export interface UserCreate {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  role?: "admin" | "standard";
  is_superuser?: boolean;
  is_active?: boolean;
}

export interface UserUpdate {
  email?: string;
  password?: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: "admin" | "standard";
  is_superuser?: boolean;
  is_active?: boolean;
  mfa_enabled?: boolean;
  force_password_change?: boolean;
  preferences?: UserPreferences;
}
