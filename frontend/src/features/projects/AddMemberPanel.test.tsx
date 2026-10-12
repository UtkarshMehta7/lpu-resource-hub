import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as DirectoryModule from "@/features/directory/api";

import { ApiError } from "@/lib/api/errors";

import { AddMemberPanel } from "./AddMemberPanel";
import type * as ProjectsApi from "./api";

const { fetchResearchers, fetchDiscoverableStudents, addMember } = vi.hoisted(() => ({
  fetchResearchers: vi.fn(),
  fetchDiscoverableStudents: vi.fn(),
  addMember: vi.fn(),
}));

vi.mock("@/features/directory/api", async (importOriginal) => ({
  ...(await importOriginal<typeof DirectoryModule>()),
  fetchResearchers,
  fetchDiscoverableStudents,
}));
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof ProjectsApi>()),
  addMember,
}));

function page<T>(items: T[]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

const RESEARCHER = {
  user_id: "u-faculty",
  registration_number: "12400112",
  full_name: "Neha Gupta",
  designation: "Assistant Professor",
  department_id: "d1",
  department_name: "Computer Science and Engineering",
  availability: "open" as const,
  verification_status: "verified" as const,
  research_areas: [],
  skills: [],
};

const STUDENT = {
  user_id: "u-student",
  registration_number: "12400124",
  full_name: "Simran Kaur",
  program: "B.Tech CSE",
  year: 3,
  department_id: "d1",
  department_name: "Computer Science and Engineering",
  interests: null,
  research_areas: [],
  skills: [],
};

function renderPanel({ memberIds = [] as string[], onAdded = vi.fn() } = {}) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <AddMemberPanel projectId="p1" memberIds={memberIds} onAdded={onAdded} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onAdded };
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchResearchers.mockResolvedValue(page([RESEARCHER]));
  fetchDiscoverableStudents.mockResolvedValue(page([STUDENT]));
});

describe("adding somebody to a team without waiting for them to apply", () => {
  it("stays out of the way until the lead asks for it", () => {
    renderPanel();

    expect(screen.getByRole("button", { name: "Add someone to the team" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Find a person")).not.toBeInTheDocument();
  });

  it("searches both the researchers and the students", async () => {
    // Most projects are adding a student; researchers and students are two
    // endpoints behind two permissions, and one list alone is the wrong half.
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Add someone to the team" }));
    await user.type(screen.getByLabelText("Find a person"), "ka");

    await waitFor(() => expect(fetchResearchers).toHaveBeenCalledWith({ q: "ka" }));
    expect(fetchDiscoverableStudents).toHaveBeenCalledWith({ q: "ka" });
    expect(await screen.findByText("Neha Gupta")).toBeInTheDocument();
    expect(screen.getByText("Simran Kaur")).toBeInTheDocument();
  });

  it("still lists researchers when the student lookup is refused", async () => {
    // STUDENT_DISCOVER is a separate permission. Failing the whole search
    // because one half is unavailable hides the half that worked.
    const user = userEvent.setup();
    fetchDiscoverableStudents.mockRejectedValue(new Error("403"));
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Add someone to the team" }));
    await user.type(screen.getByLabelText("Find a person"), "ne");

    expect(await screen.findByText("Neha Gupta")).toBeInTheDocument();
  });

  it("never offers somebody who is already on the team", async () => {
    // A picker that proposes what the submit would refuse is the trap the
    // facility-custodian candidate list exists to avoid.
    const user = userEvent.setup();
    renderPanel({ memberIds: ["u-student"] });

    await user.click(screen.getByRole("button", { name: "Add someone to the team" }));
    await user.type(screen.getByLabelText("Find a person"), "an");

    expect(await screen.findByText("Neha Gupta")).toBeInTheDocument();
    expect(screen.queryByText("Simran Kaur")).not.toBeInTheDocument();
  });

  it("sends the person and the role the lead typed", async () => {
    const user = userEvent.setup();
    // One candidate, so "Add" names exactly one button.
    fetchDiscoverableStudents.mockResolvedValue(page([]));
    const { onAdded } = renderPanel();

    await user.click(screen.getByRole("button", { name: "Add someone to the team" }));
    const role = screen.getByLabelText("Role on this project");
    await user.clear(role);
    await user.type(role, "Field lead");
    await user.type(screen.getByLabelText("Find a person"), "ne");

    await screen.findByText("Neha Gupta");
    await user.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(addMember).toHaveBeenCalledWith("p1", "u-faculty", "Field lead"));
    expect(onAdded).toHaveBeenCalled();
  });

  it("shows what the server said rather than failing silently", async () => {
    const user = userEvent.setup();
    // One candidate, so "Add" names exactly one button.
    fetchDiscoverableStudents.mockResolvedValue(page([]));
    // toApiError only unwraps the envelope off a real Axios error; anything
    // else comes back as "Unknown error". Throw what the client throws.
    addMember.mockRejectedValue(
      new ApiError("They are already on this team.", "http", 409, "conflict"),
    );
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Add someone to the team" }));
    await user.type(screen.getByLabelText("Find a person"), "ne");
    await screen.findByText("Neha Gupta");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("They are already on this team.")).toBeInTheDocument();
  });

  it("does not search on a single character", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Add someone to the team" }));
    await user.type(screen.getByLabelText("Find a person"), "n");

    await waitFor(() => expect(fetchResearchers).not.toHaveBeenCalled());
  });
});
