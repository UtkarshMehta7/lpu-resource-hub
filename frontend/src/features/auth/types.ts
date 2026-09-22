export type Role = "student" | "faculty" | "research_coordinator" | "admin";

export type SelfRegisterableRole = Extract<Role, "student" | "faculty">;

export type CoordinatorScopeType = "department" | "school" | "university";

/** Matches the backend's UserRead schema exactly (see app/modules/users/schemas.py). */
export interface UserRead {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  department_id: string | null;
  coordinator_scope_type: CoordinatorScopeType | null;
  coordinator_scope_id: string | null;
  onboarding_complete: boolean;
  created_at: string;
}

/** Matches the backend's AccessTokenResponse schema. */
export interface AccessTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserRead;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  role: SelfRegisterableRole;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}
