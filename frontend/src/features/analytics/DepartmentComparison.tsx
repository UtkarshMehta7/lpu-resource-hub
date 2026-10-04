import { useQuery } from "@tanstack/react-query";

import { SkeletonList } from "@/components/ui/Skeleton";

import { fetchDepartmentComparison } from "./api";

/**
 * Every department, side by side.
 *
 * The reason the Dean of Research role existed and could not do its job: the
 * only figure available was one institution-wide total, and a single blended
 * number hides precisely what it is wanted for. Comparing departments is the
 * job; this is the table that does it.
 *
 * Sorted by what needs attention first — overdue milestones, then at-risk —
 * because a reader working down the list should meet the problems before the
 * successes.
 */
export function DepartmentComparison() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics", "by-department"],
    queryFn: fetchDepartmentComparison,
  });

  if (isPending) return <SkeletonList rows={4} />;
  if (isError)
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load the comparison.
      </p>
    );
  if (!data.length) return <p className="text-sm text-ink-muted">No departments to compare yet.</p>;

  const ranked = [...data].sort(
    (a, b) =>
      b.milestones_overdue - a.milestones_overdue ||
      b.milestones_at_risk - a.milestones_at_risk ||
      a.department_name.localeCompare(b.department_name),
  );

  return (
    <div className="overflow-x-auto rounded-card border border-line bg-surface">
      <table className="w-full min-w-[46rem] text-sm">
        <caption className="sr-only">
          Research activity by department, those needing attention first
        </caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-muted">
            <th scope="col" className="px-4 py-3 font-medium">
              Department
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              Researchers
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              Students
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              Active projects
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              Publications
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              Overdue
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              At risk
            </th>
            <th scope="col" className="px-4 py-3 text-right font-medium">
              Awaiting verification
            </th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((row) => (
            <tr key={row.department_id} className="border-b border-line last:border-0">
              <th scope="row" className="px-4 py-3 text-left font-medium">
                {row.department_name}
                {row.school_name ? (
                  <span className="block text-xs font-normal text-ink-muted">
                    {row.school_name}
                  </span>
                ) : null}
              </th>
              <td className="px-4 py-3 text-right tabular-nums">{row.researchers}</td>
              <td className="px-4 py-3 text-right tabular-nums">{row.students}</td>
              <td className="px-4 py-3 text-right tabular-nums">{row.projects_active}</td>
              <td className="px-4 py-3 text-right tabular-nums">{row.publications}</td>
              <td
                className={`px-4 py-3 text-right tabular-nums ${
                  row.milestones_overdue ? "font-semibold text-red-700" : "text-ink-muted"
                }`}
              >
                {row.milestones_overdue}
              </td>
              <td
                className={`px-4 py-3 text-right tabular-nums ${
                  row.milestones_at_risk ? "font-semibold text-amber-700" : "text-ink-muted"
                }`}
              >
                {row.milestones_at_risk}
              </td>
              <td className="px-4 py-3 text-right tabular-nums">{row.verification_pending}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
