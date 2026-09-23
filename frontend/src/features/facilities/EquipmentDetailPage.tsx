import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import {
  deleteEquipment,
  fetchAvailability,
  fetchEquipment,
  MAINTENANCE_LABEL,
  updateEquipment,
} from "./api";
import { EditableName } from "./EditableName";
import { BookingForm } from "./BookingForm";
import { WeekCalendar } from "./WeekCalendar";
import { addDays, startOfWeek, toDateInput } from "./week";

export function EquipmentDetailPage() {
  const { equipmentId = "" } = useParams<{ equipmentId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
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

  const onError = (caught: unknown) => setError(toApiError(caught).message);

  const renameMutation = useMutation({
    mutationFn: (name: string) => updateEquipment(equipmentId, { name }),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["equipment-item", equipmentId] });
      await queryClient.invalidateQueries({ queryKey: ["equipment"] });
    },
    onError,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteEquipment(equipmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["equipment"] });
      // Back to the facility list rather than the parent facility: `equipment`
      // is gone by now, so its id is not something to rely on here.
      void navigate("/facilities", { replace: true });
    },
    onError: (caught: unknown) => {
      setConfirmingDelete(false);
      onError(caught);
    },
  });

  if (isPending) return <SkeletonList rows={2} />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Equipment not found.
      </p>
    );
  }

  const canManage = user?.role === "research_coordinator" || user?.role === "admin";

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
          <EditableName
            value={equipment.name}
            canEdit={canManage}
            isSaving={renameMutation.isPending}
            onSave={(name) => renameMutation.mutate(name)}
            label="Equipment name"
          />
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
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-line px-2 py-1 text-xs">
            {MAINTENANCE_LABEL[equipment.maintenance_status]}
          </span>
          {canManage ? (
            <button
              type="button"
              onClick={() => {
                setError(null);
                setConfirmingDelete(true);
              }}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-canvas"
            >
              Delete
            </button>
          ) : null}
        </div>
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

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this equipment?"
        description={`${equipment.name} stops being bookable. Existing bookings are not removed.`}
        isConfirming={deleteMutation.isPending}
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}
