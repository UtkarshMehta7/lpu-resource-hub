import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { fetchDepartments, fetchSchools } from "@/features/directory/api-org";
import { toApiError } from "@/lib/api/errors";

import { createDepartment, createSchool } from "./api";

/**
 * Schools and departments.
 *
 * Every scope rule on the platform is expressed in departments — who a
 * coordinator oversees, which students a faculty member may enrol, what a
 * scoped analytics query counts. The endpoints have always existed; until now
 * there was no way to reach them without curl, which left a fresh install
 * unable to appoint anybody.
 */
const FIELD = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";
const BUTTON =
  "rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50";

export function OrganisationPage() {
  const queryClient = useQueryClient();
  const [schoolName, setSchoolName] = useState("");
  const [departmentName, setDepartmentName] = useState("");
  const [schoolId, setSchoolId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: schools } = useQuery({ queryKey: ["schools"], queryFn: () => fetchSchools() });
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["schools"] });
    await queryClient.invalidateQueries({ queryKey: ["departments"] });
  };

  const schoolMutation = useMutation({
    mutationFn: (name: string) => createSchool(name),
    onSuccess: async () => {
      setSchoolName("");
      await refresh();
    },
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

  const departmentMutation = useMutation({
    mutationFn: (payload: { schoolId: string; name: string }) =>
      createDepartment(payload.schoolId, payload.name),
    onSuccess: async () => {
      setDepartmentName("");
      await refresh();
    },
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

  const schoolOf = (id: string) => schools?.find((school) => school.id === id)?.name ?? "—";

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Schools and departments</h1>
      <p className="mt-1 text-sm text-ink-muted">
        The structure everything else is scoped to. A coordinator oversees a department; faculty and
        students belong to one.
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-card border border-line bg-surface p-5">
          <h2 className="text-sm font-semibold">Schools</h2>
          <form
            className="mt-3 flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              if (schoolName.trim()) schoolMutation.mutate(schoolName.trim());
            }}
          >
            <label className="sr-only" htmlFor="school-name">
              School name
            </label>
            <input
              id="school-name"
              value={schoolName}
              onChange={(event) => setSchoolName(event.target.value)}
              placeholder="e.g. School of Computer Science"
              className={`${FIELD} flex-1`}
            />
            <button type="submit" disabled={schoolMutation.isPending} className={BUTTON}>
              Add school
            </button>
          </form>

          {schools && schools.length > 0 ? (
            <ul className="mt-4 divide-y divide-line text-sm">
              {schools.map((school) => (
                <li key={school.id} className="py-2">
                  {school.name}
                  <span className="block text-xs text-ink-muted">
                    {departments?.filter((d) => d.school_id === school.id).length ?? 0} departments
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-4">
              <EmptyState title="No schools yet">Add one to get started.</EmptyState>
            </div>
          )}
        </section>

        <section className="rounded-card border border-line bg-surface p-5">
          <h2 className="text-sm font-semibold">Departments</h2>
          <form
            className="mt-3 space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              setError(null);
              if (schoolId && departmentName.trim()) {
                departmentMutation.mutate({ schoolId, name: departmentName.trim() });
              }
            }}
          >
            <label className="sr-only" htmlFor="department-school">
              School
            </label>
            <select
              id="department-school"
              value={schoolId}
              onChange={(event) => setSchoolId(event.target.value)}
              className={FIELD}
            >
              <option value="">Choose a school</option>
              {schools?.map((school) => (
                <option key={school.id} value={school.id}>
                  {school.name}
                </option>
              ))}
            </select>
            <div className="flex flex-wrap gap-2">
              <label className="sr-only" htmlFor="department-name">
                Department name
              </label>
              <input
                id="department-name"
                value={departmentName}
                onChange={(event) => setDepartmentName(event.target.value)}
                placeholder="e.g. Computer Science"
                className={`${FIELD} flex-1`}
              />
              <button
                type="submit"
                disabled={!schoolId || departmentMutation.isPending}
                className={BUTTON}
              >
                Add department
              </button>
            </div>
          </form>

          {departments && departments.length > 0 ? (
            <ul className="mt-4 divide-y divide-line text-sm">
              {departments.map((department) => (
                <li key={department.id} className="py-2">
                  {department.name}
                  <span className="block text-xs text-ink-muted">
                    {schoolOf(department.school_id)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-4">
              <EmptyState title="No departments yet">
                A coordinator is appointed to oversee one, so this comes first.
              </EmptyState>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
