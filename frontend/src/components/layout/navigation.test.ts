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
