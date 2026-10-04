import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import { decideBooking, fetchBookingQueue } from "./api";

/**
 * Approvals, for whoever is responsible for the equipment.
 *
 * The server decides what lands here -- a department for a coordinator, the
 * assigned facilities for a custodian, everything for an admin -- so the only
 * thing the role changes on this page is the sentence describing it.
 *
 * Two overlapping requests can both sit here; approving the second one fails
 * cleanly, because the database says so.
 */
export function BookingQueuePage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["booking-queue"],
    queryFn: fetchBookingQueue,
  });

  const decide = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      decideBooking(id, action, notes[id]?.trim() || null),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["booking-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["availability"] });
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  return (
    <div>
      <PageHeader
        title="Booking requests"
        description={`${
          user?.role === "facility_custodian"
            ? "Requests for equipment in the facilities assigned to you."
            : user?.role === "admin"
              ? "Requests for equipment anywhere in the university."
              : "Requests for equipment in your department."
        } Approving a slot that someone else already holds is rejected by the database, so double-booking cannot happen.`}
      />

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
          Could not load the queue.
        </p>
      ) : null}
      {data && data.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="Nothing waiting" description="New requests will appear here." />
        </div>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.map((booking) => (
          <li key={booking.id} className="rounded-card border border-line bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Link
                to={`/equipment/${booking.equipment_id}`}
                className="text-sm font-semibold hover:underline"
              >
                {booking.equipment_name}
              </Link>
              <span className="text-xs text-ink-muted">{booking.facility_name}</span>
            </div>
            <p className="mt-1 text-xs text-ink-muted">
              {booking.user_name} · {new Date(booking.starts_at).toLocaleString()} –{" "}
              {new Date(booking.ends_at).toLocaleTimeString()}
            </p>
            <p className="mt-2 text-sm">{booking.purpose}</p>
            <label htmlFor={`note-${booking.id}`} className="mt-3 block text-xs font-medium">
              Note to the requester (optional)
            </label>
            <textarea
              id={`note-${booking.id}`}
              rows={2}
              value={notes[booking.id] ?? ""}
              onChange={(event) =>
                setNotes((prev) => ({ ...prev, [booking.id]: event.target.value }))
              }
              className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            />
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: booking.id, action: "approve" })}
                className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Approve
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: booking.id, action: "reject" })}
                className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
