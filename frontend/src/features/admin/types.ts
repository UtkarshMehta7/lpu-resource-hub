import type { Role } from "@/features/auth/types";

export type CoordinatorScopeType = "department" | "school" | "university";

/** Matches the backend's AdminUserRead schema (see app/modules/admin/schemas.py). */
export interface AdminUserRead {
  id: string;
  registration_number: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  department_id: string | null;
  coordinator_scope_type: CoordinatorScopeType | null;
  coordinator_scope_id: string | null;
  /** Who provisioned this account; null for the bootstrap admin. */
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Matches the backend's generic Page[T] response shape. */
export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminUserUpdate {
  full_name?: string;
  department_id?: string | null;
  coordinator_scope_type?: CoordinatorScopeType | null;
  coordinator_scope_id?: string | null;
}

/** Returned once, when an admin issues a replacement temporary password. */
export interface TemporaryPasswordRead {
  user: AdminUserRead;
  temporary_password: string;
}

export interface AuditLogRead {
  id: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}
