export interface RegisterPayload {
  email: string;
  password: string;
  is_active?: boolean;
  is_superuser?: boolean;
  is_verified?: boolean;
  role?: string;
}

export interface ForgotPasswordPayload {
  email: string;
}

export interface ResetPasswordPayload {
  token: string;
  password: string;
}

export interface VerifyPayload {
  token: string;
}

export interface RequestVerifyTokenPayload {
  email: string;
}
