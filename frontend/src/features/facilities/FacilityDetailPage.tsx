import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { Uid } from "@/components/ui/Uid";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import {
  assignFacilityCustodian,
  deleteFacility,
  fetchCustodianCandidates,
  fetchEquipmentList,
  fetchFacility,
  MAINTENANCE_LABEL,
  updateFacility,
} from "./api";
import { EditableName } from "./EditableName";

export function FacilityDetailPage() {
  const { facilityId = "" } = useParams<{ facilityId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const {
    data: facility,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["facility", facilityId],
    queryFn: () => fetchFacility(facilityId),
  });
  const { data: equipment } = useQuery({
    queryKey: ["equipment", { facility_id: facilityId }],
    queryFn: () => fetchEquipmentList({ facility_id: facilityId }),
  });

  const onError = (caught: unknown) => setError(toApiError(caught).message);

  const renameMutation = useMutation({
    mutationFn: (name: string) => updateFacility(facilityId, { name }),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["facility", facilityId] });
      await queryClient.invalidateQueries({ queryKey: ["facilities"] });
    },
    onError,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteFacility(facilityId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["facilities"] });
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
        Facility not found.
      </p>
    );
  }

  // Two different powers, and conflating them is what left the custodian
  // role unusable. Managing the room is object-level and a custodian has it
  // over their own; deciding WHO holds the room is department-level, and a
  // custodian deliberately has it over nobody -- otherwise they could hand
  // their facility away or seize a colleague's. The server enforces both.
  const canManage =
    user?.role === "research_coordinator" ||
    user?.role === "admin" ||
    (user?.role === "facility_custodian" && facility.custodian_id === user.id);
  const canAssignCustodian = user?.role === "research_coordinator" || user?.role === "admin";

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/facilities" className="text-sm text-brand-700 hover:underline">
        ← LPU facilities
      </Link>
      <EditableName
        value={facility.name}
        canEdit={canManage}
        isSaving={renameMutation.isPending}
        onSave={(name) => renameMutation.mutate(name)}
        label="Facility name"
      />
      <p className="mt-1 text-sm text-ink-muted">
        {[facility.department_name ?? "University-wide", facility.location, facility.contact]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {facility.description ? <p className="mt-4 text-sm">{facility.description}</p> : null}

      <div className="mt-4 rounded-card border border-line bg-surface p-4">
        <h2 className="text-sm font-semibold">Custodian</h2>
        {facility.custodian_id ? (
          <p className="mt-1 text-sm">
            {facility.custodian_name} <Uid value={facility.custodian_registration_number ?? ""} />
          </p>
        ) : (
          <p className="mt-1 text-sm text-ink-muted">
            Nobody looks after this facility yet. Bookings for its equipment fall to the
            department&apos;s coordinator until one is assigned.
          </p>
        )}
        {canAssignCustodian ? (
          <CustodianPicker
            facilityId={facility.id}
            currentId={facility.custodian_id}
            onError={setError}
          />
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {canManage ? (
        <button
          type="button"
          onClick={() => {
            setError(null);
            setConfirmingDelete(true);
          }}
          className="mt-4 rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-canvas"
        >
          Delete facility
        </button>
      ) : null}

      <section className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">Equipment</h2>
          {canManage ? (
            <Link
              to={`/facilities/${facility.id}/equipment/new`}
              className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
            >
              Add equipment
            </Link>
          ) : null}
        </div>

        {equipment && equipment.items.length === 0 ? (
          <div className="mt-2">
            <EmptyState
              title="No equipment listed yet"
              description={
                canManage
                  ? "Add the instruments in this facility so people can book them."
                  : "Nothing in this facility is bookable yet."
              }
            />
          </div>
        ) : null}

        <ul className="mt-2 space-y-2">
          {equipment?.items.map((item) => (
            <li key={item.id} className="rounded-card border border-line bg-surface p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <Link to={`/equipment/${item.id}`} className="text-sm font-medium hover:underline">
                  {item.name}
                </Link>
                <span className="rounded-md border border-line px-2 py-0.5 text-xs text-ink-muted">
                  {MAINTENANCE_LABEL[item.maintenance_status]}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">
                {[
                  item.category,
                  `up to ${item.max_hours}h`,
                  item.students_allowed ? "open to students" : "staff only",
                  item.requires_approval ? "needs approval" : "instant booking",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this facility?"
        description={`${facility.name} and everything listed under it stop being bookable. ${
          facility.equipment_count > 0
            ? `It still has ${facility.equipment_count} item${facility.equipment_count === 1 ? "" : "s"} of equipment.`
            : ""
        }`}
        isConfirming={deleteMutation.isPending}
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}

/**
 * Choose who looks after a facility, or clear it.
 *
 * The options come from the server rather than from the account list, and are
 * already filtered to the custodians eligible for this facility -- so the
 * dropdown can never offer somebody the assignment would then refuse.
 */
function CustodianPicker({
  facilityId,
  currentId,
  onError,
}: {
  facilityId: string;
  currentId: string | null;
  onError: (message: string | null) => void;
}) {
  const queryClient = useQueryClient();
  const { data: candidates } = useQuery({
    queryKey: ["custodian-candidates", facilityId],
    queryFn: () => fetchCustodianCandidates(facilityId),
  });

  const assign = useMutation({
    mutationFn: (userId: string | null) => assignFacilityCustodian(facilityId, userId),
    onSuccess: async () => {
      onError(null);
      await queryClient.invalidateQueries({ queryKey: ["facility", facilityId] });
      await queryClient.invalidateQueries({ queryKey: ["facilities"] });
    },
    onError: (caught) => onError(toApiError(caught).message),
  });

  return (
    <div className="mt-3">
      <label htmlFor="custodian" className="block text-xs font-medium">
        Assign a custodian
      </label>
      <select
        id="custodian"
        value={currentId ?? ""}
        disabled={assign.isPending}
        onChange={(event) => {
          onError(null);
          assign.mutate(event.target.value || null);
        }}
        className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm disabled:opacity-50"
      >
        <option value="">Nobody</option>
        {candidates?.map((person) => (
          <option key={person.id} value={person.id}>
            {person.full_name} ({person.registration_number})
          </option>
        ))}
      </select>
      {candidates && candidates.length === 0 ? (
        <p className="mt-1 text-xs text-ink-muted">
          No facility custodian accounts exist for this department yet.{" "}
          <Link to="/people/custodians/new" className="font-medium text-brand-700 hover:underline">
            Appoint one
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
