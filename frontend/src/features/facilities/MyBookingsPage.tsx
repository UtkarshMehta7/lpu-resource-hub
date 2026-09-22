import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { toApiError } from "@/lib/api/errors";
import { useNow } from "@/lib/useNow";

import { BOOKING_STATUS_LABEL, cancelBooking, fetchMyBookings } from "./api";

export function MyBookingsPage() {
  const queryClient = useQueryClient();
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const now = useNow();

  const { data, isPending, isError } = useQuery({
    queryKey: ["my-bookings"],
    queryFn: () => fetchMyBookings(),
  });

  const cancel = useMutation({
    mutationFn: (id: string) => cancelBooking(id),
    onSuccess: async () => {
      setCancelling(null);
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["my-bookings"] });
      await queryClient.invalidateQueries({ queryKey: ["availability"] });
    },
    onError: (caught) => {
      setCancelling(null);
      setError(toApiError(caught).message);
    },
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">My bookings</h1>
      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {isPending ? (
        <div className="mt-6">
          <SkeletonList />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load your bookings.
        </p>
      ) : null}
      {data && data.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No bookings yet"
            description="Find a lab or instrument and request a slot."
            actionLabel="Browse LPU facilities"
            actionTo="/facilities"
          />
        </div>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.map((booking) => {
          const upcoming = new Date(booking.starts_at).getTime() > now;
          const cancellable =
            upcoming && (booking.status === "pending" || booking.status === "approved");
          return (
            <li key={booking.id} className="rounded-card border border-line bg-surface p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <Link
                  to={`/equipment/${booking.equipment_id}`}
                  className="text-sm font-semibold hover:underline"
                >
                  {booking.equipment_name}
                </Link>
                <span className="rounded-md border border-line px-2 py-1 text-xs">
                  {BOOKING_STATUS_LABEL[booking.status]}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">
                {booking.facility_name} · {new Date(booking.starts_at).toLocaleString()} –{" "}
                {new Date(booking.ends_at).toLocaleTimeString()}
              </p>
              <p className="mt-2 text-sm">{booking.purpose}</p>
              {booking.decision_note ? (
                <p className="mt-1 text-xs text-ink-muted">Note: {booking.decision_note}</p>
              ) : null}
              {cancellable ? (
                <button
                  type="button"
                  onClick={() => setCancelling(booking.id)}
                  className="mt-3 text-xs text-red-700 hover:underline"
                >
                  Cancel
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>

      <ConfirmDialog
        open={cancelling !== null}
        title="Cancel this booking?"
        description="The slot goes back into the calendar for everyone else."
        confirmLabel="Cancel booking"
        cancelLabel="Keep it"
        isConfirming={cancel.isPending}
        onConfirm={() => {
          if (cancelling) cancel.mutate(cancelling);
        }}
        onCancel={() => setCancelling(null)}
      />
    </div>
  );
}
