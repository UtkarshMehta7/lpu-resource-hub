import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdministrationPage } from "./AdministrationPage";
import { OrganisationPage } from "./OrganisationPage";

const { fetchUsers, fetchSchools, fetchDepartments, createSchool, createDepartment } = vi.hoisted(
  () => ({
    fetchUsers: vi.fn(),
    fetchSchools: vi.fn(),
    fetchDepartments: vi.fn(),
    createSchool: vi.fn(),
    createDepartment: vi.fn(),
  }),
);

vi.mock("./api", () => ({ fetchUsers, createSchool, createDepartment }));
vi.mock("@/features/directory/api-org", () => ({ fetchSchools, fetchDepartments }));

function renderPage(element: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // One request per role for the active count, plus one for the deactivated
  // total. The count comes from `total`, not the page.
  fetchUsers.mockImplementation(({ role, is_active }: { role?: string; is_active?: boolean }) =>
    Promise.resolve({
      items: [],
      page: 1,
      page_size: 1,
      total:
        is_active === false
          ? 7
          : ({ research_coordinator: 1, faculty: 2, student: 40, admin: 1 }[role ?? ""] ?? 0),
    }),
  );
  fetchSchools.mockResolvedValue([{ id: "s1", name: "Engineering" }]);
  fetchDepartments.mockResolvedValue([{ id: "d1", school_id: "s1", name: "Agriculture" }]);
});

describe("AdministrationPage", () => {
  it("says what an admin provisions, and offers the one action", async () => {
    renderPage(<AdministrationPage />);

    expect(await screen.findByRole("heading", { name: "Administration" })).toBeInTheDocument();
    expect(screen.getByText(/You appoint research coordinators/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add coordinator" })).toHaveAttribute(
      "href",
      "/people/new",
    );
  });

  it("counts the platform by role", async () => {
    renderPage(<AdministrationPage />);

    // "Coordinators" is also a privilege link, so scope to the count card,
    // and wait for the query rather than reading the zero it starts at.
    const card = (await screen.findAllByRole("link", { name: /Coordinators/ }))[0];
    await waitFor(() => expect(card).toHaveTextContent("1"));
    expect(screen.getByRole("link", { name: /Faculty/ })).toHaveTextContent("2");
  });

  it("counts only accounts that can sign in, and says so", async () => {
    renderPage(<AdministrationPage />);

    // Deactivated accounts are reported, not folded into the totals.
    expect(await screen.findByText(/Accounts that can sign in/i)).toBeInTheDocument();
    expect(await screen.findByText(/7 deactivated accounts/i)).toBeInTheDocument();
    expect(fetchUsers).toHaveBeenCalledWith(
      expect.objectContaining({ role: "student", is_active: true }),
    );
  });

  it("points at the organisation first when there are no departments", async () => {
    fetchDepartments.mockResolvedValue([]);
    renderPage(<AdministrationPage />);

    expect(await screen.findByText(/Start with the organisation/i)).toBeInTheDocument();
  });

  it("does not nag when departments exist", async () => {
    renderPage(<AdministrationPage />);

    await screen.findByRole("heading", { name: "Administration" });
    expect(screen.queryByText(/Start with the organisation/i)).not.toBeInTheDocument();
  });
});

describe("OrganisationPage", () => {
  it("lists the structure that scopes everything else", async () => {
    renderPage(<OrganisationPage />);

    // The school shows in its own list and as an option on the department
    // form, so both matches are expected.
    expect(await screen.findAllByText("Engineering")).not.toHaveLength(0);
    expect(screen.getByText("Agriculture")).toBeInTheDocument();
  });

  it("cannot add a department before a school is chosen", async () => {
    renderPage(<OrganisationPage />);

    expect(await screen.findByRole("button", { name: "Add department" })).toBeDisabled();
  });
});
