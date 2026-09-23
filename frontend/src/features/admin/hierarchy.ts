import type { Role } from "@/features/auth/types";

/**
 * Which roles each role may remove, mirroring DELETABLE_ROLES on the server.
 *
 * This only decides whether to *show* the button. The server checks the same
 * rule plus the department scope, which the browser cannot evaluate, so a
 * button that appears is not a promise the deletion will be allowed — the
 * refusal is shown if it comes.
 */
export const DELETABLE_ROLES: Record<Role, readonly Role[]> = {
  admin: ["student", "faculty", "research_coordinator", "admin"],
  research_coordinator: ["student", "faculty"],
  faculty: ["student"],
  student: [],
};

export function mayDeleteRole(actorRole: Role, targetRole: Role): boolean {
  return DELETABLE_ROLES[actorRole].includes(targetRole);
}

/** Nobody deletes their own account, whatever their role. */
export function mayDelete(
  actor: { id: string; role: Role } | null | undefined,
  target: { id: string; role: Role },
): boolean {
  if (!actor || actor.id === target.id) return false;
  return mayDeleteRole(actor.role, target.role);
}
