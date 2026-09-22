import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { toApiError } from "@/lib/api/errors";

import { createBooking, type Equipment } from "./api";
import { toIso } from "./week";

/** Request (or, for instant-booking equipment, take) a slot. */
export function BookingForm({
  equipment,
  date,
  hour,
  onDateChange,
  onHourChange,
}: {
  equipment: Equipment;
  date: string;
  hour: number;
  onDateChange: (date: string) => void;
  onHourChange: (hour: number) => void;
}) {
  const queryClient = useQueryClient();
  const [hours, setHours] = useState(1);
  const [purpose, setPurpose] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  const book = useMutation({
    mutationFn: () =>
      createBooking({
        equipment_id: equipment.id,
        starts_at: toIso(date, hour),
        ends_at: toIso(date, hour + hours),
        purpose: purpose.trim(),
      }),
    onSuccess: async (booking) => {
      setError(null);
      setPurpose("");
      setConfirmation(
        booking.status === "approved"
          ? "Booked. It's on your calendar."
          : "Requested. A research coordinator will review it.",
      );
      await queryClient.invalidateQueries({ queryKey: ["availability", equipment.id] });
      await queryClient.invalidateQueries({ queryKey: ["my-bookings"] });
    },
    onError: (caught) => {
      setConfirmation(null);
      setError(toApiError(caught).message);
    },
  });

  const unavailable = equipment.maintenance_status !== "available";

  const submit = () => {
    if (purpose.trim().length < 5) {
      setError("Say briefly what you need it for.");
      return;
    }
    if (hours > equipment.max_hours) {
      setError(`This equipment can be booked for at most ${equipment.max_hours} hours.`);
      return;
    }
    book.mutate();
  };

  if (unavailable) {
    return (
      <p className="rounded-card border border-line bg-surface px-4 py-3 text-sm text-ink-muted">
        This equipment is{" "}
        {equipment.maintenance_status === "retired" ? "retired" : "under maintenance"} and
        can&apos;t be booked.
      </p>
    );
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="space-y-3"
      noValidate
    >
      {error ? (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {confirmation ? (
        <p role="status" className="text-sm text-brand-700">
          {confirmation}
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="booking-date" className="block text-sm font-medium">
            Date
          </label>
          <input
            id="booking-date"
            type="date"
            value={date}
            onChange={(event) => onDateChange(event.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="booking-hour" className="block text-sm font-medium">
            Start
          </label>
          <select
            id="booking-hour"
            value={hour}
            onChange={(event) => onHourChange(Number(event.target.value))}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          >
            {Array.from({ length: 14 }, (_, index) => index + 8).map((value) => (
              <option key={value} value={value}>
                {`${value}`.padStart(2, "0")}:00
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="booking-hours" className="block text-sm font-medium">
            Hours (max {equipment.max_hours})
          </label>
          <input
            id="booking-hours"
            inputMode="numeric"
            value={hours}
            onChange={(event) => setHours(Number(event.target.value) || 1)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div>
        <label htmlFor="booking-purpose" className="block text-sm font-medium">
          What do you need it for?
        </label>
        <textarea
          id="booking-purpose"
          rows={3}
          value={purpose}
          onChange={(event) => setPurpose(event.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
        />
      </div>

      <button
        type="submit"
        disabled={book.isPending}
        className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
      >
        {book.isPending
          ? "Sending…"
          : equipment.requires_approval
            ? "Request this slot"
            : "Book this slot"}
      </button>
      {equipment.min_lead_hours > 0 ? (
        <p className="text-xs text-ink-muted">
          Needs at least {equipment.min_lead_hours} hours&apos; notice.
        </p>
      ) : null}
    </form>
  );
}
