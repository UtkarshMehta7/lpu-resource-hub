import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminCreateAccountPage } from "./AdminCreateAccountPage";

const { createAccountAsAdmin, fetchDepartments } = vi.hoisted(() => ({
  createAccountAsAdmin: vi.fn(),
  fetchDepartments: vi.fn(),
}));

vi.mock("./api", () => ({ createAccountAsAdmin }));
vi.mock("@/features/directory/api-org", () => ({ fetchDepartments }));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminCreateAccountPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDepartments.mockResolvedValue([{ id: "dept-1", name: "School of Computer Science" }]);
  createAccountAsAdmin.mockResolvedValue({
    user: { id: "u1", full_name: "Rohit Sharma", role: "facility_custodian" },
    temporary_password: "Temp-1234",
  });
});

describe("AdminCreateAccountPage", () => {
  it("offers every role an administrator may appoint", async () => {
    renderPage();
    const roles = screen.getByLabelText("Role", { exact: true });

    for (const label of [
      "Student",
      "Faculty / researcher",
      "Research coordinator",
      "Facility custodian",
      "Dean of Research",
    ]) {
      expect(await screen.findByRole("option", { name: label })).toBeInTheDocument();
    }
    expect(roles).toBeInTheDocument();
  });

  it("never offers Administrator, because promotion takes two people", () => {
    renderPage();

    expect(screen.queryByRole("option", { name: "Administrator" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Administrators" })).toHaveAttribute(
      "href",
      "/admin/administrators",
    );
  });

  it("stops asking for a department once the role is dean, who has none", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByLabelText("Role", { exact: true }), "dean_of_research");

    expect(screen.getByText("(not needed for a dean)")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "None" })).toBeInTheDocument();
  });

  it("still asks for a department for a custodian, who looks after one department's rooms", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.selectOptions(screen.getByLabelText("Role", { exact: true }), "facility_custodian");

    expect(screen.getByRole("option", { name: "Choose a department" })).toBeInTheDocument();
    expect(screen.getByText(/approve bookings for those/i)).toBeInTheDocument();
  });

  it("sends the chosen role and shows the temporary password once", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("option", { name: "School of Computer Science" });
    await user.selectOptions(screen.getByLabelText("Role", { exact: true }), "facility_custodian");
    await user.type(screen.getByLabelText("Registration number"), "12400999");
    await user.type(screen.getByLabelText("Full name"), "Rohit Sharma");
    await user.selectOptions(screen.getByLabelText(/Department/), "dept-1");
    await user.click(screen.getByRole("button", { name: /Create facility custodian/i }));

    await waitFor(() =>
      expect(createAccountAsAdmin).toHaveBeenCalledWith({
        registration_number: "12400999",
        full_name: "Rohit Sharma",
        role: "facility_custodian",
        department_id: "dept-1",
        email: null,
      }),
    );
    expect(await screen.findByText("Temp-1234")).toBeInTheDocument();
    expect(screen.getByText("This is shown once.")).toBeInTheDocument();
  });
});
