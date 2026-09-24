import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Uid } from "@/components/ui/Uid";

import { fetchMyDepartment } from "./api";

/**
 * Who oversees your department, and a way through to their profile.
 *
 * Your coordinator verifies your profile, reviews your projects and approves
 * your bookings. Until now the only way to find out who that was, or to reach
 * them, was to ask somebody — which is a strange gap in a platform whose whole
 * point is that people should be findable.
 */
export function DepartmentCoordinatorCard() {
  const { data, isPending } = useQuery({
    queryKey: ["me", "department"],
    queryFn: fetchMyDepartment,
  });

  if (isPending || !data) return null;

  return (
    <section className="mt-4 rounded-card border border-line bg-surface px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {data.department_name}
      </p>

      {data.user_id ? (
        <p className="mt-1 text-sm">
          Overseen by{" "}
          <Link
            to={`/researchers/${data.user_id}`}
            className="font-medium text-brand-700 hover:underline"
          >
            {data.full_name}
          </Link>{" "}
          {data.registration_number ? <Uid value={data.registration_number} /> : null}
          {data.designation ? <span className="text-ink-muted"> · {data.designation}</span> : null}
        </p>
      ) : (
        // Saying so beats silence: it explains why nothing is being verified.
        <p className="mt-1 text-sm text-ink-muted">
          No research coordinator has been appointed for this department yet, so there is nobody to
          verify profiles or review projects here. An administrator can appoint one.
        </p>
      )}
    </section>
  );
}
