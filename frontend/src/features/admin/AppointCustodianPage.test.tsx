import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/features/auth/types";

import { AppointCustodianPage } from "./AppointCustodianPage";

const { appointFacilityCustodian, fetchDepartments, useAuthMock } = vi.hoisted(() => ({
  appointFacilityCustodian: vi.fn(),
  fetchDepartments: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", () => ({ appointFacilityCustodian }));
vi.mock("@/features/directory/api-org", () => ({ fetchDepartments }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const DEPARTMENTS = [
  { id: "d1", name: "Aerospace Engineering", school_id: "s1" },
  { id: "d2", name: "Architecture", school_id: "s1" },
];

function renderPage(role: Role, departmentId: string | null) {
  useAuthMock.mockReturnValue({
    user: { id: "u1", role, full_name: "Signed in", department_id: departmentId },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppointCustodianPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDepartments.mockResolvedValue(DEPARTMENTS);
  appointFacilityCustodian.mockResolvedValue({
    user: { id: "c1", full_name: "Harjit Sandhu", role: "facility_custodian" },
    temporary_password: "Temp-9876",
  });
});

describe("AppointCustodianPage", () => {
  it("offers no role to choose, because the endpoint fixes it", async () => {
    renderPage("research_coordinator", "d1");

    await screen.findByLabelText("Full name", { exact: true });
    expect(screen.queryByLabelText("Role", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Administrator" })).not.toBeInTheDocument();
  });

  it("fixes a coordinator to their own department", async () => {
    const user = userEvent.setup();
    renderPage("research_coordinator", "d1");

    const field = await screen.findByDisplayValue("Aerospace Engineering");
    expect(field).toBeDisabled();

    await user.type(screen.getByLabelText("Registration number"), "12499001");
    await user.type(screen.getByLabelText("Full name", { exact: true }), "Harjit Sandhu");
    await user.click(screen.getByRole("button", { name: "Appoint custodian" }));

    await waitFor(() =>
      expect(appointFacilityCustodian).toHaveBeenCalledWith({
        registration_number: "12499001",
        full_name: "Harjit Sandhu",
        // Never sent by a coordinator: the server applies their own.
        department_id: null,
        email: null,
      }),
    );
  });

  it("lets an administrator choose the department", async () => {
    const user = userEvent.setup();
    renderPage("admin", null);

    await screen.findByRole("option", { name: "Architecture" });
    await user.type(screen.getByLabelText("Registration number"), "12499002");
    await user.type(screen.getByLabelText("Full name", { exact: true }), "Kiran Bedi");
    await user.selectOptions(screen.getByLabelText("Department", { exact: true }), "d2");
    await user.click(screen.getByRole("button", { name: "Appoint custodian" }));

    await waitFor(() => expect(appointFacilityCustodian).toHaveBeenCalled());
    const sent = appointFacilityCustodian.mock.calls[0]?.[0] as { department_id: string | null };
    expect(sent.department_id).toBe("d2");
  });

  it("shows the temporary password once and points at the next step", async () => {
    const user = userEvent.setup();
    renderPage("research_coordinator", "d1");

    await screen.findByDisplayValue("Aerospace Engineering");
    await user.type(screen.getByLabelText("Registration number"), "12499003");
    await user.type(screen.getByLabelText("Full name", { exact: true }), "Harjit Sandhu");
    await user.click(screen.getByRole("button", { name: "Appoint custodian" }));

    expect(await screen.findByText("Temp-9876")).toBeInTheDocument();
    expect(screen.getByText(/shown once/i)).toBeInTheDocument();
    // An appointed custodian with no rooms does nothing, so say what is next.
    expect(screen.getByRole("link", { name: "give them a facility" })).toHaveAttribute(
      "href",
      "/facilities",
    );
  });
});
