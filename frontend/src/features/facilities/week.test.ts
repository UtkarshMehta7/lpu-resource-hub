import { describe, expect, it } from "vitest";

import { addDays, hourCell, isPast, slotFor, startOfWeek, toDateInput, toIso } from "./week";

const MONDAY = new Date(2026, 8, 21, 14, 30); // 21 Sep 2026 is a Monday
const SUNDAY = new Date(2026, 8, 27, 9, 0);

describe("startOfWeek", () => {
  it("returns Monday midnight for any day of that week", () => {
    expect(startOfWeek(MONDAY).getTime()).toBe(new Date(2026, 8, 21).getTime());
    // Sunday belongs to the week that began six days earlier, not the next one.
    expect(startOfWeek(SUNDAY).getTime()).toBe(new Date(2026, 8, 21).getTime());
  });
});

describe("slotFor", () => {
  const day = new Date(2026, 8, 21);
  const busy = [
    {
      starts_at: new Date(2026, 8, 21, 10, 0).toISOString(),
      ends_at: new Date(2026, 8, 21, 12, 0).toISOString(),
      is_mine: true,
    },
  ];

  it("marks every hour the booking covers", () => {
    expect(slotFor(busy, day, 10)?.is_mine).toBe(true);
    expect(slotFor(busy, day, 11)?.is_mine).toBe(true);
  });

  it("treats periods as half-open, so the end hour is free again", () => {
    expect(slotFor(busy, day, 9)).toBeUndefined();
    expect(slotFor(busy, day, 12)).toBeUndefined();
  });

  it("ignores other days", () => {
    expect(slotFor(busy, addDays(day, 1), 10)).toBeUndefined();
  });
});

describe("isPast", () => {
  const day = new Date(2026, 8, 21);

  it("compares against the supplied time, not the clock", () => {
    const noon = new Date(2026, 8, 21, 12, 0).getTime();
    expect(isPast(day, 9, noon)).toBe(true);
    expect(isPast(day, 12, noon)).toBe(false);
  });

  it("treats an unknown time (0) as 'not past'", () => {
    expect(isPast(day, 9, 0)).toBe(false);
  });
});

describe("toIso / toDateInput", () => {
  it("round-trips a local date and hour", () => {
    const input = toDateInput(new Date(2026, 8, 21));
    expect(input).toBe("2026-09-21");
    const iso = toIso(input, 9);
    const parsed = new Date(iso);
    expect(parsed.getHours()).toBe(9);
    expect(toDateInput(parsed)).toBe("2026-09-21");
  });

  it("keeps a cell's start and end one hour apart", () => {
    const { start, end } = hourCell(new Date(2026, 8, 21), 23);
    expect(end.getTime() - start.getTime()).toBe(60 * 60 * 1000);
  });
});
