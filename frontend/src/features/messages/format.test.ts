import { describe, expect, it } from "vitest";

import { clockTime, dayLabel, initials, relativeTime } from "./format";

describe("initials", () => {
  it("takes at most two", () => {
    expect(initials("Demo Faculty 07")).toBe("DF");
    expect(initials("Priya")).toBe("P");
  });

  it("does not crash on an empty name", () => {
    expect(initials("   ")).toBe("?");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-09-24T12:00:00Z");

  it("is short enough to read at a glance", () => {
    expect(relativeTime("2026-09-24T11:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-09-24T11:55:00Z", now)).toBe("5m");
    expect(relativeTime("2026-09-24T09:00:00Z", now)).toBe("3h");
  });

  it("returns nothing for a value it cannot read", () => {
    expect(relativeTime("not a date", now)).toBe("");
  });
});

describe("dayLabel", () => {
  const now = new Date("2026-09-24T12:00:00Z");

  it("names today and yesterday rather than dating them", () => {
    expect(dayLabel("2026-09-24T08:00:00Z", now)).toBe("Today");
    expect(dayLabel("2026-09-23T08:00:00Z", now)).toBe("Yesterday");
  });

  it("dates anything older", () => {
    expect(dayLabel("2026-09-01T08:00:00Z", now)).not.toBe("Today");
  });
});

describe("clockTime", () => {
  it("renders a time", () => {
    expect(clockTime("2026-09-24T12:00:00Z")).toMatch(/\d/);
  });
});
