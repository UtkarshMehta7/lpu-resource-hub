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
