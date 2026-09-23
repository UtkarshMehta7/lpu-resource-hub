import { describe, expect, it } from "vitest";

import type { Role } from "@/features/auth/types";

import { mayDelete, mayDeleteRole } from "./hierarchy";

const ROLES: Role[] = ["student", "faculty", "research_coordinator", "admin"];

describe("mayDeleteRole", () => {
  it("lets an administrator remove any role", () => {
    for (const role of ROLES) {
      expect(mayDeleteRole("admin", role)).toBe(true);
    }
  });

  it("lets a coordinator remove faculty and students, nobody at their level or above", () => {
    expect(mayDeleteRole("research_coordinator", "faculty")).toBe(true);
    expect(mayDeleteRole("research_coordinator", "student")).toBe(true);
    expect(mayDeleteRole("research_coordinator", "research_coordinator")).toBe(false);
    expect(mayDeleteRole("research_coordinator", "admin")).toBe(false);
  });

  it("lets a faculty member remove only students", () => {
    expect(mayDeleteRole("faculty", "student")).toBe(true);
    expect(mayDeleteRole("faculty", "faculty")).toBe(false);
    expect(mayDeleteRole("faculty", "research_coordinator")).toBe(false);
    expect(mayDeleteRole("faculty", "admin")).toBe(false);
  });

  it("lets a student remove nobody", () => {
    for (const role of ROLES) {
      expect(mayDeleteRole("student", role)).toBe(false);
    }
  });
});

describe("mayDelete", () => {
  it("refuses your own account whatever your role", () => {
    const me = { id: "u1", role: "admin" as Role };

    expect(mayDelete(me, me)).toBe(false);
    expect(mayDelete(me, { id: "u2", role: "admin" })).toBe(true);
  });

  it("refuses when nobody is signed in", () => {
    expect(mayDelete(null, { id: "u2", role: "student" })).toBe(false);
  });
});
