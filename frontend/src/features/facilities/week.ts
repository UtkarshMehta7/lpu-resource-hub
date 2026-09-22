/** Week-calendar maths, kept separate from the component so it can be tested. */

export const DAY_START_HOUR = 8;
export const DAY_END_HOUR = 21; // exclusive: the last row is 20:00-21:00
export const HOURS: number[] = Array.from(
  { length: DAY_END_HOUR - DAY_START_HOUR },
  (_, index) => DAY_START_HOUR + index,
);

export interface Slot {
  starts_at: string;
  ends_at: string;
  is_mine: boolean;
}

/** Monday of the week containing `date`, at local midnight. */
export function startOfWeek(date: Date): Date {
  const monday = new Date(date);
  monday.setHours(0, 0, 0, 0);
  // getDay(): 0 = Sunday, so Sunday belongs to the week that began 6 days ago.
  const offset = (monday.getDay() + 6) % 7;
  monday.setDate(monday.getDate() - offset);
  return monday;
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function weekDays(weekStart: Date): Date[] {
  return Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
}

export function hourCell(day: Date, hour: number): { start: Date; end: Date } {
  const start = new Date(day);
  start.setHours(hour, 0, 0, 0);
  const end = new Date(start);
  end.setHours(hour + 1);
  return { start, end };
}

/** Which busy slot covers this hour, if any. Periods are half-open. */
export function slotFor(slots: Slot[], day: Date, hour: number): Slot | undefined {
  const { start, end } = hourCell(day, hour);
  return slots.find((slot) => {
    const slotStart = new Date(slot.starts_at).getTime();
    const slotEnd = new Date(slot.ends_at).getTime();
    return slotStart < end.getTime() && slotEnd > start.getTime();
  });
}

/** `now` is passed in so callers don't read the clock while rendering. */
export function isPast(day: Date, hour: number, now: number): boolean {
  return now > 0 && hourCell(day, hour).end.getTime() <= now;
}

/** "2026-09-23" in local time, for a date input. */
export function toDateInput(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Local date + hour as an ISO instant the API can parse. */
export function toIso(dateInput: string, hour: number): string {
  const [year, month, day] = dateInput.split("-").map(Number);
  const date = new Date(year ?? 0, (month ?? 1) - 1, day ?? 1, hour, 0, 0, 0);
  return date.toISOString();
}
