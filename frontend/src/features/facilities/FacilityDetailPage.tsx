import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";

import { fetchEquipmentList, fetchFacility, MAINTENANCE_LABEL } from "./api";

export function FacilityDetailPage() {
  const { facilityId = "" } = useParams<{ facilityId: string }>();
  const { user } = useAuth();

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

  if (isPending) return <SkeletonList rows={2} />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Facility not found.
      </p>
    );
  }

  const canManage = user?.role === "research_coordinator" || user?.role === "admin";

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/facilities" className="text-sm text-brand-700 hover:underline">
        ← LPU facilities
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{facility.name}</h1>
      <p className="mt-1 text-sm text-ink-muted">
        {[facility.location, facility.contact].filter(Boolean).join(" · ")}
      </p>
      {facility.description ? <p className="mt-4 text-sm">{facility.description}</p> : null}

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
    </div>
  );
}
