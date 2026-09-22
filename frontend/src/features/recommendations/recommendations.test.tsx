import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe as suite, expect, it, vi } from "vitest";

import { describe } from "./describe";
import { RecommendationsPage } from "./RecommendationsPage";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));

vi.mock("./api", () => ({
  fetchRecommendations: fetchMock,
  RECOMMENDATION_TABS: [
    { value: "opportunities", label: "Opportunities" },
    { value: "projects", label: "Projects" },
    { value: "researchers", label: "Researchers" },
    { value: "collaborators", label: "Collaborators" },
  ],
}));

const opportunity = {
  id: "o1",
  title: "Field assistant",
  opportunity_type: "research_assistant" as const,
  status: "open" as const,
  project_id: null,
  project_title: null,
  department_id: null,
  created_by: "u1",
  creator_name: "Dr. Demo",
  positions: 2,
  accepted_count: 1,
  deadline: "2026-12-01",
  skills: [],
};

suite("describe", () => {
  it("summarises each card type and links to the right page", () => {
    expect(describe(opportunity)).toEqual({
      title: "Field assistant",
      subtitle: "Research assistant · deadline 2026-12-01 · 1/2 filled",
      to: "/opportunities/o1",
    });
    expect(
      describe({
        id: "p1",
        title: "Soil sensors",
        summary: "s",
        status: "active",
        owner_id: "u1",
        owner_name: "Dr. Demo",
        department_id: null,
        start_date: null,
        end_date: null,
        research_areas: [],
        skills: [],
      }).to,
    ).toBe("/projects/p1");
    expect(
      describe({
        user_id: "u9",
        full_name: "Dr. Demo",
        designation: "Professor",
        department_id: null,
        availability: "available",
        verification_status: "verified",
        research_areas: [],
        skills: [],
      }),
    ).toEqual({ title: "Dr. Demo", subtitle: "Professor", to: "/researchers/u9" });
  });
});

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <RecommendationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

suite("RecommendationsPage", () => {
  it("shows the score and the reasons behind each suggestion", async () => {
    fetchMock.mockResolvedValue({
      type: "opportunities",
      cold_start: false,
      items: [
        {
          item_id: "o1",
          score: 0.6936,
          reasons: ["Matches 2 of 2 required skills: Python, Sensors", "Related terms: soil"],
          item: opportunity,
        },
      ],
    });
    renderPage();

    expect(await screen.findByText("Field assistant")).toBeInTheDocument();
    expect(screen.getByText("Match 0.69")).toBeInTheDocument();
    expect(screen.getByText("Matches 2 of 2 required skills: Python, Sensors")).toBeInTheDocument();
    expect(screen.getByText("Related terms: soil")).toBeInTheDocument();
  });

  it("explains a cold start instead of showing scores", async () => {
    fetchMock.mockResolvedValue({
      type: "opportunities",
      cold_start: true,
      items: [
        {
          item_id: "o1",
          score: 0,
          reasons: ["Your profile is still incomplete, so this is simply one of the newest items"],
          item: opportunity,
        },
      ],
    });
    renderPage();

    expect(await screen.findByText(/profile is still sparse/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Match /)).toBeNull();
  });
});
