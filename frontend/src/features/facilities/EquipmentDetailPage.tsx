import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { SkeletonList } from "@/components/ui/Skeleton";

import { fetchAvailability, fetchEquipment, MAINTENANCE_LABEL } from "./api";
import { BookingForm } from "./BookingForm";
import { WeekCalendar } from "./WeekCalendar";
import { addDays, startOfWeek, toDateInput } from "./week";

export function EquipmentDetailPage() {
  const { equipmentId = "" } = useParams<{ equipmentId: string }>();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [date, setDate] = useState(() => toDateInput(new Date()));
  const [hour, setHour] = useState(9);

  const {
    data: equipment,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["equipment-item", equipmentId],
    queryFn: () => fetchEquipment(equipmentId),
  });
  const { data: availability } = useQuery({
    queryKey: ["availability", equipmentId, weekStart.toISOString()],
    queryFn: () =>
      fetchAvailability(equipmentId, weekStart.toISOString(), addDays(weekStart, 7).toISOString()),
  });

  if (isPending) return <SkeletonList rows={2} />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Equipment not found.
      </p>
    );
  }

  return (
    <div>
      <Link
        to={`/facilities/${equipment.facility_id}`}
        className="text-sm text-brand-700 hover:underline"
      >
        ← {equipment.facility_name}
      </Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{equipment.name}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {[
              equipment.category,
              `up to ${equipment.max_hours}h per booking`,
              equipment.students_allowed ? "open to students" : "staff only",
              equipment.requires_approval ? "needs approval" : "instant booking",
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <span className="rounded-md border border-line px-2 py-1 text-xs">
          {MAINTENANCE_LABEL[equipment.maintenance_status]}
        </span>
      </div>
      {equipment.description ? <p className="mt-4 text-sm">{equipment.description}</p> : null}

      <section className="mt-8">
        <WeekCalendar
          weekStart={weekStart}
          busy={availability?.busy ?? []}
          onWeekChange={setWeekStart}
          onPick={(pickedDate, pickedHour) => {
            setDate(pickedDate);
            setHour(pickedHour);
          }}
        />
        <p className="mt-2 text-xs text-ink-muted">
          Only approved bookings block a slot. Pick a free hour to fill in the form below.
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-base font-semibold">
          {equipment.requires_approval ? "Request a slot" : "Book a slot"}
        </h2>
        <div className="mt-3">
          <BookingForm
            equipment={equipment}
            date={date}
            hour={hour}
            onDateChange={setDate}
            onHourChange={setHour}
          />
        </div>
      </section>
    </div>
  );
}
