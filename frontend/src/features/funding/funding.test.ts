import { describe, expect, it } from "vitest";

import { amountLabel, daysUntil, type FundingCall } from "./api";

function call(overrides: Partial<FundingCall> = {}): FundingCall {
  return {
    id: "f1",
    organization: "Demo Research Council",
    title: "Demo seed grant",
    description: "A fictional demo call.",
    eligibility: null,
    amount_text: null,
    amount_min: null,
    amount_max: null,
    deadline: "2026-10-01",
    official_source_url: null,
    status: "open",
    is_demo: true,
    research_areas: [],
    created_at: "",
    ...overrides,
  };
}

describe("daysUntil", () => {
  const noon = new Date(2026, 8, 24, 12, 0).getTime(); // 24 Sep 2026

  it("counts whole days to the deadline", () => {
    expect(daysUntil("2026-09-25", noon)).toBe(1);
    expect(daysUntil("2026-10-01", noon)).toBe(7);
  });

  it("goes negative once the deadline has passed", () => {
    expect(daysUntil("2026-09-23", noon)).toBe(-1);
  });

  it("returns null before the clock is known, so nothing renders wrongly", () => {
    expect(daysUntil("2026-10-01", 0)).toBeNull();
  });
});

describe("amountLabel", () => {
  it("prefers the free-text amount", () => {
    expect(amountLabel(call({ amount_text: "Up to a demo amount", amount_max: 5 }))).toBe(
      "Up to a demo amount",
    );
  });

  it("formats a range, and one-sided bounds", () => {
    // Grouping follows the viewer's locale (Indian grouping for an LPU user),
    // so the expectation is built the same way rather than hard-coded.
    const fifty = (50000).toLocaleString();
    const hundredFifty = (150000).toLocaleString();
    expect(amountLabel(call({ amount_min: 50000, amount_max: 150000 }))).toBe(
      `${fifty} – ${hundredFifty}`,
    );
    expect(amountLabel(call({ amount_max: 150000 }))).toBe(`up to ${hundredFifty}`);
    expect(amountLabel(call({ amount_min: 50000 }))).toBe(`from ${fifty}`);
  });

  it("says nothing when no amount is given", () => {
    expect(amountLabel(call())).toBeNull();
  });
});
