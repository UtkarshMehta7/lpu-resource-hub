import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

const { fetchMock, authState } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  authState: {
    user: { id: "u1", full_name: "Demo Student", role: "student" },
  },
}));

vi.mock("./api", () => ({ fetchDashboard: fetchMock }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: () => authState }));

const emptyResponse = {
  role: "student",
  onboarding_complete: true,
  student: null,
  faculty: null,
  coordinator: null,
  admin: null,
};

function renderDashboard() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  beforeEach(() => fetchMock.mockReset());

  it("shows a student their applications, deadlines and matches", async () => {
    fetchMock.mockResolvedValue({
      ...emptyResponse,
      student: {
        recommended_opportunities: [
          {
            id: "o1",
            title: "Field assistant",
            deadline: "2026-12-01",
            positions: 2,
            accepted_count: 0,
          },
        ],
        recommended_projects: [],
        recommended_researchers: [],
        saved_count: 2,
        applications_by_status: { submitted: 1, under_review: 1, accepted: 1 },
        pending_collaboration_requests: 3,
        upcoming_deadlines: [
          {
            opportunity_id: "o1",
            title: "Field assistant",
            deadline: "2026-12-01",
            applied: true,
          },
        ],
      },
    });
    renderDashboard();

    expect(screen.getByText("Welcome back, Demo")).toBeInTheDocument();
    expect((await screen.findByText("open applications")).nextSibling).toHaveTextContent("2");
    expect(screen.getByText("saved").nextSibling).toHaveTextContent("2");
    expect(screen.getByText("Closes 2026-12-01 · applied")).toBeInTheDocument();
  });

  it("tells an empty student dashboard what to do next", async () => {
    fetchMock.mockResolvedValue({
      ...emptyResponse,
      onboarding_complete: false,
      student: {
        recommended_opportunities: [],
        recommended_projects: [],
        recommended_researchers: [],
        saved_count: 0,
        applications_by_status: {},
        pending_collaboration_requests: 0,
        upcoming_deadlines: [],
      },
    });
    renderDashboard();

    expect(await screen.findByText(/finish onboarding/i)).toBeInTheDocument();
    expect(screen.getByText("No deadlines coming up")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /browse opportunities/i })).toBeInTheDocument();
  });

  it("shows coordinator queues, not student sections", async () => {
    authState.user = { id: "u2", full_name: "Demo Coordinator", role: "research_coordinator" };
    fetchMock.mockResolvedValue({
      ...emptyResponse,
      role: "research_coordinator",
      faculty: {
        my_projects: [],
        projects_by_status: {},
        open_opportunities: [],
        pending_applications: 0,
        team_members: 0,
        accepted_collaborations: 0,
        publications: 0,
        pending_collaboration_requests: 0,
      },
      coordinator: {
        pending_verifications: [
          { user_id: "u9", full_name: "Dr. Waiting", designation: "Assistant Professor" },
        ],
        pending_reviews: [],
        open_reports: 4,
        department_activity: { new_projects: 2, new_opportunities: 1, new_applications: 5 },
      },
    });
    renderDashboard();

    expect(await screen.findByText("Dr. Waiting")).toBeInTheDocument();
    expect(screen.getByText("open reports").nextSibling).toHaveTextContent("4");
    expect(screen.getByText("new projects").nextSibling).toHaveTextContent("2");
    expect(screen.queryByText("Upcoming deadlines")).toBeNull();
  });
});

describe("the roles outside the provisioning chain", () => {
  it("gives a dean a dashboard instead of an empty page", async () => {
    // It had sections for student, faculty, coordinator and admin and none
    // for a dean, so the role signed in to nothing at all.
    fetchMock.mockResolvedValue({
      role: "dean_of_research",
      onboarding_complete: true,
      student: null,
      faculty: null,
      coordinator: null,
      admin: null,
      custodian: null,
      dean: {
        departments: 8,
        departments_needing_attention: 3,
        projects_at_risk: 7,
        pending_cross_department_reviews: 2,
        verification_backlog: 5,
        active_projects: 11,
        researchers: 44,
      },
    });
    renderDashboard();

    expect(await screen.findByText("The institution")).toBeInTheDocument();
    expect(screen.getByText("Slipping")).toBeInTheDocument();
    // Every figure links to where it can be acted on.
    expect(screen.getByRole("link", { name: "Compare departments" })).toHaveAttribute(
      "href",
      "/analytics",
    );
    expect(screen.getByRole("link", { name: "At-risk projects" })).toHaveAttribute(
      "href",
      "/coordinator/at-risk",
    );
    expect(screen.getByRole("link", { name: "Review queue" })).toHaveAttribute(
      "href",
      "/coordinator/review-queue",
    );
  });

  it("gives a custodian the rooms they hold", async () => {
    fetchMock.mockResolvedValue({
      role: "facility_custodian",
      onboarding_complete: true,
      student: null,
      faculty: null,
      coordinator: null,
      admin: null,
      dean: null,
      custodian: { facilities_held: 2, equipment: 6, bookings_awaiting_decision: 3 },
    });
    renderDashboard();

    expect(await screen.findByText("In your care")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Booking requests" })).toHaveAttribute(
      "href",
      "/coordinator/booking-queue",
    );
  });
});

describe("the announcements section", () => {
  const notice = (overrides: Record<string, unknown> = {}) => ({
    id: "a1",
    subject: "Invention disclosure window closes on Friday",
    body: "Send your disclosures to the IP cell before 5 pm.",
    audience: "institution",
    department_id: null,
    department_name: null,
    posted_by: "u-admin",
    posted_by_name: "Harpreet Kaur",
    posted_by_role: "admin",
    status: "published",
    published_at: "2026-10-09T09:00:00Z",
    links: [],
    attachments: [],
    unread: true,
    created_at: "2026-10-09T08:00:00Z",
    updated_at: "2026-10-09T09:00:00Z",
    ...overrides,
  });

  it("shows the latest notices to a student, who may not post", async () => {
    authState.user = { id: "u1", full_name: "Demo Student", role: "student" };
    fetchMock.mockResolvedValue({
      ...emptyResponse,
      announcements: { unread: 1, latest: [notice()] },
    });

    renderDashboard();

    expect(
      await screen.findByText("Invention disclosure window closes on Friday"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 unread")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All announcements" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Post a notice" })).not.toBeInTheDocument();
  });

  it("offers posting to a role that may", async () => {
    authState.user = { id: "u2", full_name: "Demo Dean", role: "dean_of_research" };
    fetchMock.mockResolvedValue({
      ...emptyResponse,
      role: "dean_of_research",
      announcements: { unread: 0, latest: [notice({ unread: false })] },
    });

    renderDashboard();

    expect(await screen.findByRole("link", { name: "Post a notice" })).toBeInTheDocument();
    // No pill when there is nothing unread -- a "0 unread" badge is noise.
    expect(screen.queryByText(/unread/)).not.toBeInTheDocument();
  });

  it("marks an unread notice with a word, not only a colour", async () => {
    authState.user = { id: "u1", full_name: "Demo Student", role: "student" };
    fetchMock.mockResolvedValue({
      ...emptyResponse,
      announcements: { unread: 1, latest: [notice()] },
    });

    renderDashboard();

    expect(await screen.findByText("New")).toBeInTheDocument();
  });

  it("points at the history when there is nothing to show", async () => {
    authState.user = { id: "u1", full_name: "Demo Student", role: "student" };
    fetchMock.mockResolvedValue({ ...emptyResponse, announcements: { unread: 0, latest: [] } });

    renderDashboard();

    expect(await screen.findByText(/Nothing has been announced lately/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Search older announcements" })).toBeInTheDocument();
  });

  it("survives an API that has never heard of the field", async () => {
    // Netlify serves the new bundle in seconds; Render rebuilds in minutes.
    // In that window this code meets an older API. Reading `.latest` off
    // `undefined` inside render would throw and take the WHOLE dashboard
    // down for every role -- the prior-art panel's bug on a worse page.
    authState.user = { id: "u1", full_name: "Demo Student", role: "student" };
    const older = { ...emptyResponse };
    delete (older as Record<string, unknown>).announcements;
    fetchMock.mockResolvedValue(older);

    renderDashboard();

    // Awaited on the section, not on "Welcome back": that heading is static
    // and renders before the query resolves, so awaiting it would assert
    // against the loading state and pass for the wrong reason.
    expect(await screen.findByText(/Nothing has been announced lately/)).toBeInTheDocument();
    // And the rest of the dashboard is still standing.
    expect(screen.getByText(/Welcome back/)).toBeInTheDocument();
  });
});
