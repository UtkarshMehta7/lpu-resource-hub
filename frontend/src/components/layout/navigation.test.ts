import { describe, expect, it } from "vitest";

import { NAV, navigationFor, searchNavigation } from "./navigation";

describe("navigationFor", () => {
  it("offers a student only what a student can reach", () => {
    const labels = navigationFor("student").map((item) => item.label);

    expect(labels).toContain("Messages");
    expect(labels).toContain("Projects");
    expect(labels).not.toContain("Accounts");
    expect(labels).not.toContain("Verification");
  });

  it("offers an administrator the administration group", () => {
    const labels = navigationFor("admin").map((item) => item.label);

    expect(labels).toContain("Audit log");
    expect(labels).toContain("Administrators");
  });

  it("gives a dean the figures and none of the queues they cannot act in", () => {
    const labels = navigationFor("dean_of_research").map((item) => item.label);

    expect(labels).toContain("Analytics");
    expect(labels).toContain("Research report");
    expect(labels).toContain("At-risk projects");
    // Every other Review entry is an action on somebody's work.
    expect(labels).not.toContain("Verification");
    expect(labels).not.toContain("Reviews");
    expect(labels).not.toContain("Bookings");
    expect(labels).not.toContain("Accounts");
  });

  it("gives a custodian the booking queue and nothing else to review", () => {
    const labels = navigationFor("facility_custodian").map((item) => item.label);

    expect(labels).toContain("Facilities");
    expect(labels).toContain("Bookings");
    expect(labels).not.toContain("Verification");
    expect(labels).not.toContain("Analytics");
    expect(labels).not.toContain("My people");
  });

  it("lets an administrator reach the only page that creates a custodian", () => {
    // /admin/accounts/new is the sole route that names a role, so it is the
    // only way to make a facility custodian or a dean. It was reachable from
    // one tile on /admin and nowhere else -- so it was absent from the top
    // bar, the full menu and the command palette, and people could not find
    // it. That is the failure this file exists to prevent.
    const admin = navigationFor("admin");

    expect(admin.map((item) => item.to)).toContain("/admin/accounts/new");
    // And findable by what somebody would actually type.
    for (const query of ["custodian", "dean"]) {
      expect(searchNavigation(admin, query).map((item) => item.to)).toContain(
        "/admin/accounts/new",
      );
    }
  });

  it("every route a role can reach is in this list", () => {
    // The list drives three different ways around the app; a destination
    // missing here is reachable through none of them.
    for (const role of ["admin", "research_coordinator", "faculty"] as const) {
      for (const item of navigationFor(role)) {
        expect(item.to.startsWith("/")).toBe(true);
      }
    }
  });

  it("gives a signed-out visitor nothing", () => {
    expect(navigationFor(undefined)).toEqual([]);
  });

  it("puts every destination in a group, so none can hide from the menu", () => {
    for (const item of NAV) {
      expect(item.group).toBeTruthy();
    }
  });
});

describe("searchNavigation", () => {
  const items = navigationFor("admin");

  it("prefers a label that starts with what was typed", () => {
    // "pro" must offer Projects before Profile.
    const [first] = searchNavigation(items, "pro");

    expect(first?.label).toBe("Projects");
  });

  it("finds a page by a word that is not in its label", () => {
    const labels = searchNavigation(items, "verify").map((item) => item.label);

    expect(labels).toContain("Verification");
  });

  it("finds the chat by the word people actually use for it", () => {
    const labels = searchNavigation(items, "chat").map((item) => item.label);

    expect(labels).toContain("Messages");
  });

  it("returns everything for an empty query", () => {
    expect(searchNavigation(items, "   ")).toHaveLength(items.length);
  });

  it("returns nothing for a query that matches nothing", () => {
    expect(searchNavigation(items, "zzzzz")).toEqual([]);
  });

  it("never offers a page the role cannot reach", () => {
    const studentResults = searchNavigation(navigationFor("student"), "account");

    expect(studentResults.map((item) => item.label)).not.toContain("Accounts");
  });
});
