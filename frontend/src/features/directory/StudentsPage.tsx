import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { fetchDiscoverableStudents } from "./api";

/** Faculty/coordinator/admin only. The backend returns opted-in students only. */
export function StudentsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";

  const { data, isPending, isError } = useQuery({
    queryKey: ["students", q],
    queryFn: () => fetchDiscoverableStudents({ q: q || undefined }),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Discover students</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Students who have opted in to being discoverable. Nobody else appears here.
      </p>

      <input
        type="search"
        aria-label="Search students"
        defaultValue={q}
        placeholder="Name, programme or interests"
        onChange={(event) => {
          const next = new URLSearchParams(searchParams);
          if (event.target.value) {
            next.set("q", event.target.value);
          } else {
            next.delete("q");
          }
          setSearchParams(next);
        }}
        className="mt-4 w-full max-w-md rounded-md border border-line bg-surface px-3 py-2 text-sm"
      />

      {isPending ? <p className="mt-6 text-sm text-ink-muted">Loading students…</p> : null}

      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load students.
        </p>
      ) : null}

      {data && data.items.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          No discoverable students match this search.
        </p>
      ) : null}

      {data && data.items.length > 0 ? (
        <>
          <p className="mt-6 text-sm text-ink-muted">{data.total} students</p>
          <ul className="mt-3 space-y-3">
            {data.items.map((student) => (
              <li key={student.user_id} className="rounded-card border border-line bg-surface p-4">
                <p className="text-sm font-semibold">{student.full_name}</p>
                <p className="text-sm text-ink-muted">
                  {student.program} · Year {student.year}
                </p>
                {student.interests ? (
                  <p className="mt-2 text-sm text-ink-muted">{student.interests}</p>
                ) : null}
                {student.skills.length > 0 ? (
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {student.skills.slice(0, 5).map((skill) => (
                      <li
                        key={skill}
                        className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted"
                      >
                        {skill}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
