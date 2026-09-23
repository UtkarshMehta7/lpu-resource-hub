import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PeoplePage } from "./PeoplePage";
import type { AdminUserRead } from "./types";

const { fetchManageableUsers, fetchDeletionImpact, deleteUser, fetchDepartments, useAuthMock } =
  vi.hoisted(() => ({
    fetchManageableUsers: vi.fn(),
    fetchDeletionImpact: vi.fn(),
    deleteUser: vi.fn(),
    fetchDepartments: vi.fn(),
    useAuthMock: vi.fn(),
  }));

vi.mock("./api", () => ({ fetchManageableUsers, fetchDeletionImpact, deleteUser }));
vi.mock("@/features/directory/api-org", () => ({ fetchDepartments }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const STUDENT: AdminUserRead = {
  id: "s1",
  registration_number: "12400942",
  email: null,
  full_name: "Demo Student 01",
  role: "student",
  is_active: true,
  must_change_password: false,
  department_id: "dept-1",
  coordinator_scope_type: null,
  coordinator_scope_id: null,
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PeoplePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "f1", role: "faculty" } });
  fetchManageableUsers.mockResolvedValue({ items: [STUDENT], page: 1, page_size: 100, total: 1 });
  fetchDepartments.mockResolvedValue([{ id: "dept-1", name: "Agriculture", school_id: "sc1" }]);
  deleteUser.mockResolvedValue(undefined);
  fetchDeletionImpact.mockResolvedValue({
    registration_number: "12400942",
    full_name: "Demo Student 01",
    role: "student",
    projects_owned: 0,
    project_memberships: 0,
    opportunities_created: 0,
    publications_created: 0,
    applications_submitted: 1,
    collaboration_requests: 0,
    bookings: 0,
    reports_filed: 0,
    accounts_provisioned: 0,
    destroys_content: true,
  });
});

describe("PeoplePage", () => {
  it("lists the people in your scope with their UID and department", async () => {
    renderPage();

    expect(await screen.findByText("Demo Student 01")).toBeInTheDocument();
    expect(screen.getByText("12400942")).toBeInTheDocument();
    expect(screen.getByText("Agriculture")).toBeInTheDocument();
  });

  it("deletes only after the confirmation, and says what goes with it", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /delete demo student 01/i }));
    expect(deleteUser).not.toHaveBeenCalled();
    expect(await screen.findByText("1 applications they submitted")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /delete permanently/i }));

    await waitFor(() => expect(deleteUser).toHaveBeenCalledWith("s1"));
  });

  it("does nothing when the confirmation is dismissed", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /delete demo student 01/i }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(deleteUser).not.toHaveBeenCalled();
  });

  it("surfaces the reason the server refused", async () => {
    const user = userEvent.setup();
    deleteUser.mockRejectedValue(new Error("nope"));
    renderPage();

    await user.click(await screen.findByRole("button", { name: /delete demo student 01/i }));
    await user.click(screen.getByRole("button", { name: /delete permanently/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("tells a coordinator with an empty list where to look", async () => {
    useAuthMock.mockReturnValue({ user: { id: "c1", role: "research_coordinator" } });
    fetchManageableUsers.mockResolvedValue({ items: [], page: 1, page_size: 100, total: 0 });
    renderPage();

    expect(
      await screen.findByText(/ask an administrator to check the department/i),
    ).toBeInTheDocument();
  });
});
