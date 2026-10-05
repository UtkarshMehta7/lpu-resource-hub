import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewQueuePage } from "./ReviewQueuePage";
import type { ProjectCard } from "./api";

const { fetchReviewQueue, reviewProject, useAuthMock } = vi.hoisted(() => ({
  fetchReviewQueue: vi.fn(),
  reviewProject: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", () => ({ fetchReviewQueue, reviewProject }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

function project(overrides: Partial<ProjectCard> = {}): ProjectCard {
  return {
    id: "p1",
    title: "Soil sensors",
    summary: "Cheap sensors for farms.",
    status: "pending_review",
    owner_id: "u1",
    owner_name: "Dr. Demo",
    owner_registration_number: "12400113",
    department_id: "d1",
    department_name: "Agriculture",
    spans_departments: [],
    start_date: null,
    end_date: null,
    research_areas: [],
    skills: [],
    ...overrides,
  };
}

function renderQueue() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ReviewQueuePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "u9", role: "research_coordinator" } });
  fetchReviewQueue.mockResolvedValue([project()]);
});

describe("ReviewQueuePage", () => {
  it("tells a coordinator the queue is their department's", async () => {
    renderQueue();

    expect(await screen.findByText(/submitted for review in your scope/i)).toBeInTheDocument();
    expect(screen.queryByText(/reaches across departments/i)).toBeNull();
  });

  it("tells a dean the queue is the work that crosses departments", async () => {
    // A dean saw a page identical to a coordinator's, with nothing saying why
    // these projects were theirs to decide (ADR 0032).
    useAuthMock.mockReturnValue({ user: { id: "u9", role: "dean_of_research" } });
    renderQueue();

    expect(await screen.findByText(/reaches across departments/i)).toBeInTheDocument();
    expect(screen.getByText(/is its coordinator's to decide, not yours/i)).toBeInTheDocument();
  });

  it("names the departments a project reaches into", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u9", role: "dean_of_research" } });
    fetchReviewQueue.mockResolvedValue([project({ spans_departments: ["Chemistry", "Physics"] })]);
    renderQueue();

    // Why this project is the dean's, said on the card itself rather than
    // left to be worked out from the team page.
    expect(await screen.findByText("Also Chemistry and Physics")).toBeInTheDocument();
    expect(screen.getByText(/no single coordinator sees all of it/i)).toBeInTheDocument();
  });

  it("says nothing about crossing for work inside one department", async () => {
    renderQueue();

    await screen.findByText("Soil sensors");
    expect(screen.queryByText(/^Also /)).toBeNull();
  });
});
