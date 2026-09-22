import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";

import {
  fetchDashboard,
  type AdminDashboard,
  type CoordinatorDashboard,
  type FacultyDashboard,
  type StudentDashboard,
} from "./api";

export function DashboardPage() {
  const { user } = useAuth();
  const { data, isPending, isError } = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">
        {user ? `Welcome back, ${user.full_name.split(" ")[0]}` : "Dashboard"}
      </h1>

      {isPending ? (
        <div className="mt-6">
          <SkeletonList rows={4} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load your dashboard.
        </p>
      ) : null}

      {data && !data.onboarding_complete ? (
        <div className="mt-6 rounded-card border border-line bg-surface px-4 py-3 text-sm">
          Your profile is incomplete, so matches will be rough.{" "}
          <Link to="/onboarding" className="text-brand-700 hover:underline">
            Finish onboarding
          </Link>
        </div>
      ) : null}

      {data?.student ? <StudentSections data={data.student} /> : null}
      {data?.faculty ? <FacultySections data={data.faculty} /> : null}
      {data?.coordinator ? <CoordinatorSections data={data.coordinator} /> : null}
      {data?.admin ? <AdminSections data={data.admin} /> : null}
    </div>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: { label: string; to: string };
  children: ReactNode;
}) {
  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {action ? (
          <Link to={action.to} className="text-sm text-brand-700 hover:underline">
            {action.label}
          </Link>
        ) : null}
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Stats({ entries }: { entries: [string, number | string][] }) {
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {entries.map(([label, value]) => (
        <div key={label} className="rounded-card border border-line bg-surface p-4">
          <dt className="text-xs text-ink-muted capitalize">{label.replace(/_/g, " ")}</dt>
          <dd className="mt-1 text-xl font-semibold">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CardList({
  items,
  empty,
}: {
  items: { to: string; title: string; subtitle?: string }[];
  empty: ReactNode;
}) {
  if (items.length === 0) return <>{empty}</>;
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.to + item.title} className="rounded-card border border-line bg-surface p-3">
          <Link to={item.to} className="text-sm font-medium hover:underline">
            {item.title}
          </Link>
          {item.subtitle ? <p className="text-xs text-ink-muted">{item.subtitle}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function StudentSections({ data }: { data: StudentDashboard }) {
  const open =
    (data.applications_by_status.submitted ?? 0) +
    (data.applications_by_status.under_review ?? 0) +
    (data.applications_by_status.shortlisted ?? 0);
  return (
    <>
      <Section title="At a glance">
        <Stats
          entries={[
            ["open applications", open],
            ["accepted", data.applications_by_status.accepted ?? 0],
            ["saved", data.saved_count],
            ["requests waiting", data.pending_collaboration_requests],
          ]}
        />
      </Section>

      <Section title="Upcoming deadlines">
        <CardList
          items={data.upcoming_deadlines.map((deadline) => ({
            to: `/opportunities/${deadline.opportunity_id}`,
            title: deadline.title,
            subtitle: `Closes ${deadline.deadline}${deadline.applied ? " · applied" : " · saved"}`,
          }))}
          empty={
            <EmptyState
              title="No deadlines coming up"
              description="Apply to or save an opportunity and it will show up here."
              actionLabel="Browse opportunities"
              actionTo="/opportunities"
            />
          }
        />
      </Section>

      <Section title="Opportunities for you" action={{ label: "See all", to: "/recommendations" }}>
        <CardList
          items={data.recommended_opportunities.map((opportunity) => ({
            to: `/opportunities/${opportunity.id}`,
            title: opportunity.title,
            subtitle: `Closes ${opportunity.deadline}`,
          }))}
          empty={
            <EmptyState
              title="No matches yet"
              description="Add your skills and research areas to get suggestions."
              actionLabel="Edit profile"
              actionTo="/profile"
            />
          }
        />
      </Section>

      <Section title="Projects and researchers to explore">
        <CardList
          items={[
            ...data.recommended_projects.map((project) => ({
              to: `/projects/${project.id}`,
              title: project.title,
              subtitle: `Led by ${project.owner_name}`,
            })),
            ...data.recommended_researchers.map((researcher) => ({
              to: `/researchers/${researcher.user_id}`,
              title: researcher.full_name,
              subtitle: researcher.designation,
            })),
          ]}
          empty={<EmptyState title="Nothing to suggest yet" />}
        />
      </Section>
    </>
  );
}

function FacultySections({ data }: { data: FacultyDashboard }) {
  return (
    <>
      <Section title="At a glance">
        <Stats
          entries={[
            ["pending applications", data.pending_applications],
            ["team members", data.team_members],
            ["publications", data.publications],
            ["requests waiting", data.pending_collaboration_requests],
          ]}
        />
      </Section>

      <Section title="My projects" action={{ label: "All projects", to: "/projects/mine" }}>
        <CardList
          items={data.my_projects.map((project) => ({
            to: `/projects/${project.id}`,
            title: project.title,
            subtitle: project.status.replace(/_/g, " "),
          }))}
          empty={
            <EmptyState
              title="No projects yet"
              description="Create a project to post opportunities and build a team."
              actionLabel="New project"
              actionTo="/projects/new"
            />
          }
        />
      </Section>

      <Section
        title="Open opportunities"
        action={{ label: "My postings", to: "/opportunities/mine" }}
      >
        <CardList
          items={data.open_opportunities.map((opportunity) => ({
            to: `/opportunities/${opportunity.id}/applicants`,
            title: opportunity.title,
            subtitle: `${opportunity.accepted_count}/${opportunity.positions} filled · closes ${opportunity.deadline}`,
          }))}
          empty={
            <EmptyState
              title="Nothing open"
              description="Post an opportunity on one of your active projects."
              actionLabel="New opportunity"
              actionTo="/opportunities/new"
            />
          }
        />
      </Section>
    </>
  );
}

function CoordinatorSections({ data }: { data: CoordinatorDashboard }) {
  return (
    <>
      <Section title="Department activity (30 days)">
        <Stats
          entries={[
            ...Object.entries(data.department_activity),
            ["open reports", data.open_reports],
          ]}
        />
      </Section>

      <Section
        title="Waiting for verification"
        action={{ label: "Verification queue", to: "/coordinator/verification-queue" }}
      >
        <CardList
          items={data.pending_verifications.map((item) => ({
            to: `/researchers/${item.user_id}`,
            title: item.full_name,
            subtitle: item.designation,
          }))}
          empty={<EmptyState title="No researchers waiting" />}
        />
      </Section>

      <Section
        title="Projects awaiting review"
        action={{ label: "Review queue", to: "/coordinator/review-queue" }}
      >
        <CardList
          items={data.pending_reviews.map((project) => ({
            to: `/projects/${project.id}`,
            title: project.title,
            subtitle: `Led by ${project.owner_name}`,
          }))}
          empty={<EmptyState title="Nothing to review" />}
        />
      </Section>
    </>
  );
}

function AdminSections({ data }: { data: AdminDashboard }) {
  return (
    <>
      <Section title="Users" action={{ label: "Manage users", to: "/admin/users" }}>
        <Stats entries={Object.entries(data.users_by_role)} />
      </Section>

      <Section title="Platform">
        <Stats entries={Object.entries(data.platform_counts)} />
      </Section>

      <Section title="Moderation" action={{ label: "Reported content", to: "/admin/reports" }}>
        <Stats entries={[["open reports", data.open_reports]]} />
      </Section>

      <Section title="Recent activity">
        <ul className="space-y-1 text-sm">
          {data.recent_audit.map((entry) => (
            <li key={entry.id} className="text-ink-muted">
              <span className="font-medium text-ink">{entry.action}</span> · {entry.entity_type} ·{" "}
              {new Date(entry.created_at).toLocaleString()}
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
