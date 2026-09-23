import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as Api from "./api";
import { applicationStages, statusCounts, type CollaborationNetwork } from "./api";
import { NetworkGraph } from "./NetworkGraph";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof Api>();
  return { ...actual, fetchOverview: vi.fn(), fetchNetwork: vi.fn() };
});

describe("applicationStages", () => {
  it("orders the funnel and fills gaps with zero", () => {
    const stages = applicationStages({ applications_submitted: 3, applications_accepted: 1 });

    expect(stages.map((stage) => stage.label)).toEqual([
      "Submitted",
      "Under review",
      "Shortlisted",
      "Accepted",
      "Rejected",
      "Withdrawn",
    ]);
    expect(stages[0]?.count).toBe(3);
    expect(stages[1]?.count).toBe(0);
    expect(stages[3]?.count).toBe(1);
  });
});

describe("statusCounts", () => {
  it("drops empty buckets and makes labels readable", () => {
    expect(statusCounts({ active: 2, pending_review: 1, archived: 0 })).toEqual([
      { label: "active", count: 2 },
      { label: "pending review", count: 1 },
    ]);
  });
});

function graph(overrides: Partial<CollaborationNetwork> = {}): CollaborationNetwork {
  return {
    scope: "platform",
    nodes: [
      {
        id: "a",
        full_name: "Dr. Demo",
        role: "faculty",
        department_id: null,
        degree: 1,
        connected: true,
      },
      {
        id: "b",
        full_name: "Demo Student",
        role: "student",
        department_id: null,
        degree: 1,
        connected: true,
      },
      {
        id: "c",
        full_name: "Nobody Connected",
        role: "faculty",
        department_id: null,
        degree: 0,
        connected: false,
      },
    ],
    edges: [{ source: "a", target: "b", kinds: ["project"], weight: 2 }],
    ...overrides,
  };
}

describe("NetworkGraph", () => {
  it("draws only the connected people and labels the picture", () => {
    render(<NetworkGraph graph={graph()} />);

    expect(screen.getByRole("img", { name: /2 people, 1 connections/i })).toBeInTheDocument();
    expect(screen.getByText("Dr. Demo")).toBeInTheDocument();
    expect(screen.getByText("Demo Student")).toBeInTheDocument();
    // Someone with no connections isn't drawn floating in space.
    expect(screen.queryByText("Nobody Connected")).toBeNull();
  });

  it("explains itself when there is nothing to draw", () => {
    render(<NetworkGraph graph={graph({ nodes: [], edges: [] })} />);

    expect(screen.getByText(/no connections yet/i)).toBeInTheDocument();
  });
});

describe("AnalyticsPage", () => {
  it("renders scoped copy for a coordinator", async () => {
    const { fetchOverview, fetchNetwork } = await import("./api");
    vi.mocked(fetchOverview).mockResolvedValue({
      scope: "department",
      department_id: "d1",
      projects_by_status: { active: 2 },
      projects_by_area: [{ label: "Soil Science", count: 2 }],
      opportunity_funnel: { opportunities_open: 1, applications_submitted: 1 },
      equipment_utilisation: [{ label: "Probe", hours: 6, bookings: 3 }],
      funding_interest: [],
      verification_backlog: { pending: 2, oldest_waiting_since: null },
      accepted_collaborations: 4,
      open_reports: 0,
      trends: [{ month: "2026-09", projects: 2, applications: 1, bookings: 3 }],
    });
    vi.mocked(fetchNetwork).mockResolvedValue(graph({ scope: "department" }));

    const { AnalyticsPage } = await import("./AnalyticsPage");
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AnalyticsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/for your department only/i)).toBeInTheDocument();
    expect(screen.getByText("Awaiting verification").nextSibling).toHaveTextContent("2");
    expect(screen.getByText(/Probe · 3 bookings/)).toBeInTheDocument();
  });
});
