import type { DeletionImpact } from "./types";

/** What the cascade will take, so it is never a surprise afterwards. */
export function DeletionDetails({
  impact,
  loading,
}: {
  impact: DeletionImpact | undefined;
  loading: boolean;
}) {
  if (loading) {
    return <p className="text-sm text-ink-muted">Checking what else would be deleted…</p>;
  }
  if (!impact) return null;

  const destroyed: string[] = [
    [impact.projects_owned, "project", "projects they lead"],
    [impact.opportunities_created, "opportunity", "opportunities they posted"],
    [impact.publications_created, "publication", "publications they added"],
    [impact.applications_submitted, "application", "applications they submitted"],
    [impact.project_memberships, "membership", "project memberships"],
    [impact.collaboration_requests, "request", "collaboration requests"],
    [impact.bookings, "booking", "facility bookings"],
    [impact.reports_filed, "report", "reports they filed"],
  ]
    .filter(([count]) => (count as number) > 0)
    .map(([count, , label]) => `${count as number} ${label as string}`);

  return (
    <div className="rounded-md border border-line bg-canvas p-3 text-sm">
      {destroyed.length === 0 ? (
        <p>This account has no work attached to it, so nothing else is deleted with it.</p>
      ) : (
        <>
          <p className="font-medium text-red-700">Deleted along with the account:</p>
          <ul className="mt-1 list-disc pl-5">
            {destroyed.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
      {impact.accounts_provisioned > 0 ? (
        <p className="mt-2 text-ink-muted">
          The {impact.accounts_provisioned}{" "}
          {impact.accounts_provisioned === 1 ? "account" : "accounts"} they created will keep
          working; they simply stop recording who created them.
        </p>
      ) : null}
    </div>
  );
}
