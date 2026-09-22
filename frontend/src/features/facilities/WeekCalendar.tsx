import { useNow } from "@/lib/useNow";

import {
  addDays,
  HOURS,
  isPast,
  slotFor,
  startOfWeek,
  toDateInput,
  weekDays,
  type Slot,
} from "./week";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** A week of hourly cells. Busy hours are blocked; free ones are pickable. */
export function WeekCalendar({
  weekStart,
  busy,
  onWeekChange,
  onPick,
}: {
  weekStart: Date;
  busy: Slot[];
  onWeekChange: (next: Date) => void;
  onPick: (date: string, hour: number) => void;
}) {
  const days = weekDays(weekStart);
  const now = useNow();

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">
          Week of {weekStart.toLocaleDateString(undefined, { day: "numeric", month: "long" })}
        </h2>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onWeekChange(addDays(weekStart, -7))}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
          >
            ← Previous
          </button>
          <button
            type="button"
            onClick={() => onWeekChange(startOfWeek(new Date()))}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
          >
            This week
          </button>
          <button
            type="button"
            onClick={() => onWeekChange(addDays(weekStart, 7))}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
          >
            Next →
          </button>
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-3xl border-collapse text-xs">
          <caption className="sr-only">
            Hourly availability. Booked hours are marked; free hours can be selected.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="w-14 p-1 text-left font-medium text-ink-muted">
                Time
              </th>
              {days.map((day, index) => (
                <th key={day.toISOString()} scope="col" className="p-1 font-medium">
                  {DAY_NAMES[index]} {day.getDate()}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {HOURS.map((hour) => (
              <tr key={hour}>
                <th scope="row" className="p-1 text-left font-normal text-ink-muted">
                  {`${hour}`.padStart(2, "0")}:00
                </th>
                {days.map((day) => {
                  const slot = slotFor(busy, day, hour);
                  const past = isPast(day, hour, now);
                  const label = `${day.toLocaleDateString()} ${hour}:00`;
                  if (slot) {
                    return (
                      <td key={day.toISOString()} className="p-0.5">
                        <span
                          className={`block rounded px-1 py-1.5 text-center ${
                            slot.is_mine
                              ? "bg-brand-200 text-brand-800"
                              : "bg-line/70 text-ink-muted"
                          }`}
                        >
                          {slot.is_mine ? "Yours" : "Booked"}
                        </span>
                      </td>
                    );
                  }
                  return (
                    <td key={day.toISOString()} className="p-0.5">
                      <button
                        type="button"
                        disabled={past}
                        aria-label={`Book ${label}`}
                        onClick={() => onPick(toDateInput(day), hour)}
                        className="block w-full rounded border border-line bg-surface px-1 py-1.5 text-center text-ink-muted hover:bg-brand-50 disabled:opacity-40"
                      >
                        {past ? "—" : "Free"}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
