import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as RouterModuleType from "react-router-dom";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/features/auth/types";

import { FacilityFormPage } from "./FacilityFormPage";

type RouterModule = typeof RouterModuleType;

const { createFacility, fetchDepartments, useAuthMock, navigateMock } = vi.hoisted(() => ({
  createFacility: vi.fn(),
  fetchDepartments: vi.fn(),
  useAuthMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("./api", () => ({ createFacility }));
vi.mock("@/features/directory/api-org", () => ({ fetchDepartments }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<RouterModule>()),
  useNavigate: () => navigateMock,
}));

const DEPARTMENTS = [
  { id: "d1", name: "School of Computer Science", school_id: "s1" },
  { id: "d2", name: "Department of Agriculture", school_id: "s1" },
];

function renderPage(role: Role, departmentId: string | null) {
  useAuthMock.mockReturnValue({
    user: { id: "u1", role, full_name: "Signed in", department_id: departmentId },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FacilityFormPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDepartments.mockResolvedValue(DEPARTMENTS);
  createFacility.mockResolvedValue({ id: "f1", name: "New Lab" });
});

describe("FacilityFormPage", () => {
  it("lets an administrator choose the department", async () => {
    const user = userEvent.setup();
    // An admin belongs to no department, which is exactly why they must pick.
    renderPage("admin", null);

    await screen.findByRole("option", { name: "Department of Agriculture" });
    await user.type(screen.getByLabelText("Name", { exact: true }), "New Lab");
    await user.selectOptions(screen.getByLabelText("Department", { exact: true }), "d2");
    await user.click(screen.getByRole("button", { name: "Create facility" }));

    await waitFor(() =>
      expect(createFacility).toHaveBeenCalledWith({
        name: "New Lab",
        description: null,
        department_id: "d2",
        location: null,
        contact: null,
      }),
    );
  });

  it("refuses to submit until a department is actually chosen", async () => {
    const user = userEvent.setup();
    // The bug this replaces: the form sent the admin's own department_id,
    // which is null, so every facility an admin made came out
    // university-wide without anyone asking for that.
    renderPage("admin", null);

    await screen.findByRole("option", { name: "School of Computer Science" });
    await user.type(screen.getByLabelText("Name", { exact: true }), "First Lab");
    await user.click(screen.getByRole("button", { name: "Create facility" }));

    expect(
      await screen.findByText("Choose which department runs this facility"),
    ).toBeInTheDocument();
    expect(createFacility).not.toHaveBeenCalled();
  });

  it("offers university-wide as an explicit choice, with its consequence spelled out", async () => {
    const user = userEvent.setup();
    renderPage("admin", null);

    await screen.findByRole("option", { name: /University-wide/ });
    expect(
      screen.getByText(/nobody but an administrator will be able to manage it/i),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Name", { exact: true }), "Central Instrumentation");
    await user.selectOptions(screen.getByLabelText("Department", { exact: true }), "");
    await user.click(screen.getByRole("button", { name: "Create facility" }));

    await waitFor(() => expect(createFacility).toHaveBeenCalled());
    const sent = createFacility.mock.calls[0]?.[0] as { department_id: string | null };
    expect(sent.department_id).toBeNull();
  });

  it("fixes a coordinator to the department they oversee, and does not offer a choice", async () => {
    renderPage("research_coordinator", "d1");

    // Wait for the department list, which is what resolves the name.
    const field = await screen.findByDisplayValue("School of Computer Science");
    expect(field).toBeDisabled();
    expect(
      screen.queryByRole("option", { name: "Department of Agriculture" }),
    ).not.toBeInTheDocument();
  });
});
