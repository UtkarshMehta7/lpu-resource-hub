import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/features/auth/types";

import type * as ApiModule from "./api";
import type { OpportunityCard } from "./api";
import { ProjectOpenings } from "./ProjectOpenings";

const { fetchOpportunities, useAuthMock } = vi.hoisted(() => ({
  fetchOpportunities: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  fetchOpportunities,
}));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const DAY = 24 * 60 * 60 * 1000;

function inDays(days: number): string {
  return new Date(Date.now() + days * DAY).toISOString().slice(0, 10);
}

function opening(overrides: Partial<OpportunityCard> = {}): OpportunityCard {
  return {
    id: "o1",
    title: "Field assistant for soil sensors",
    opportunity_type: "research_assistant",
    status: "open",
    project_id: "p1",
    project_title: "Low-cost soil moisture sensors",
    department_id: "d1",
    created_by: "u-faculty",
    creator_name: "Demo Faculty",
    creator_registration_number: "12500201",
    positions: 2,
    accepted_count: 0,
    deadline: inDays(30),
    skills: [],
    ...overrides,
  };
}

function page(items: OpportunityCard[]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

function signedInAs(role: Role) {
  useAuthMock.mockReturnValue({ user: { id: "u-me", role, full_name: "Somebody" } });
}

function renderSection({ isOwner = false } = {}) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <ProjectOpenings projectId="p1" isOwner={isOwner} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchOpportunities.mockResolvedValue(page([]));
});

describe("openings on a project", () => {
  it("asks only for this project's OPEN openings", async () => {
    // A draft belongs to its author and a closed one is not a way in, so
    // listing either here would offer a door that does not open.
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening()]));

    renderSection();

    await waitFor(() =>
      expect(fetchOpportunities).toHaveBeenCalledWith({
        project_id: "p1",
        status: "open",
      }),
    );
  });

  it("gives a student the way in that the project page used to lack", async () => {
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening()]));

    renderSection();

    const link = await screen.findByRole("link", {
      name: /Field assistant for soil sensors/,
    });
    expect(link).toHaveAttribute("href", "/opportunities/o1");
    expect(screen.getByText(/Open the position you want and apply from there/)).toBeInTheDocument();
  });

  it("says how many places are left, not just how many there are", async () => {
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening({ positions: 3, accepted_count: 1 })]));

    renderSection();

    expect(await screen.findByText(/2 of 3 places left/)).toBeInTheDocument();
  });

  it("says so when every place is taken", async () => {
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening({ positions: 2, accepted_count: 2 })]));

    renderSection();

    expect(await screen.findByText(/All places taken/)).toBeInTheDocument();
  });

  it("flags a deadline inside the week, because that is what decides it", async () => {
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening({ deadline: inDays(3) })]));

    renderSection();

    expect(await screen.findByText("Closing soon")).toBeInTheDocument();
  });

  it("does not flag one that is comfortably away", async () => {
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening({ deadline: inDays(40) })]));

    renderSection();

    expect(await screen.findByText(/Field assistant/)).toBeInTheDocument();
    expect(screen.queryByText("Closing soon")).not.toBeInTheDocument();
  });

  it("stays off the page entirely when there is nothing to act on", async () => {
    // An empty heading on every project anybody reads is noise.
    signedInAs("student");

    renderSection();

    await waitFor(() => expect(fetchOpportunities).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Open positions" })).not.toBeInTheDocument();
  });

  it("but tells the owner they can post one", async () => {
    signedInAs("faculty");

    renderSection({ isOwner: true });

    expect(await screen.findByRole("heading", { name: "Open positions" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Post an opening" })).toBeInTheDocument();
  });

  it("does not offer posting to somebody who may not", async () => {
    // A student can own nothing here, but the check is on the permission
    // rather than on ownership alone.
    signedInAs("student");
    fetchOpportunities.mockResolvedValue(page([opening()]));

    renderSection({ isOwner: true });

    expect(await screen.findByText(/Field assistant/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Post an opening" })).not.toBeInTheDocument();
  });

  it("does not tell a custodian how to apply, because they cannot", async () => {
    signedInAs("facility_custodian");
    fetchOpportunities.mockResolvedValue(page([opening()]));

    renderSection();

    expect(await screen.findByText(/Field assistant/)).toBeInTheDocument();
    expect(
      screen.queryByText(/Open the position you want and apply from there/),
    ).not.toBeInTheDocument();
  });

  it("degrades to a sentence rather than breaking the project page", async () => {
    signedInAs("student");
    fetchOpportunities.mockRejectedValue(new Error("boom"));

    renderSection({ isOwner: true });

    expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
  });
});
