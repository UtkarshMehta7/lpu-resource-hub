export type Role = "student" | "faculty" | "research_coordinator" | "admin";

// Students don't self-register: their department creates the account.
export type SelfRegisterableRole = Extract<Role, "faculty">;

export type CoordinatorScopeType = "department" | "school" | "university";

/** Matches the backend's UserRead schema exactly (see app/modules/users/schemas.py). */
export interface UserRead {
  id: string;
  /** The LPU registration number: what you sign in with. */
  registration_number: string;
  /** Optional contact address; never a credential. */
  email: string | null;
  full_name: string;
  role: Role;
  is_active: boolean;
  department_id: string | null;
  coordinator_scope_type: CoordinatorScopeType | null;
  coordinator_scope_id: string | null;
  onboarding_complete: boolean;
  /** True until a temporary password is replaced; the app is locked until then. */
  must_change_password: boolean;
  created_at: string;
}

/** Matches the backend's AccessTokenResponse schema. */
export interface AccessTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserRead;
}

/** Which sign-in page the request came from; the server enforces the rule. */
export type Portal = "admin" | "main";

export interface LoginPayload {
  registration_number: string;
  password: string;
  portal?: Portal;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}
