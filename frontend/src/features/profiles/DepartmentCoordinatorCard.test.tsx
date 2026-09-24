import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DepartmentCoordinatorCard } from "./DepartmentCoordinatorCard";

const { fetchMyDepartment } = vi.hoisted(() => ({ fetchMyDepartment: vi.fn() }));
vi.mock("./api", () => ({ fetchMyDepartment }));

function renderCard() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <DepartmentCoordinatorCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchMyDepartment.mockResolvedValue({
    department_id: "d1",
    department_name: "Computer Science and Engineering",
    user_id: "u9",
    full_name: "Rajesh Khanna",
    registration_number: "12400101",
    designation: "Professor",
    email: "rajesh@example.edu",
  });
});

describe("DepartmentCoordinatorCard", () => {
  it("names the coordinator and links to their profile", async () => {
    renderCard();

    const link = await screen.findByRole("link", { name: "Rajesh Khanna" });
    expect(link).toHaveAttribute("href", "/researchers/u9");
    expect(screen.getByText("12400101")).toBeInTheDocument();
    expect(screen.getByText(/Professor/)).toBeInTheDocument();
    expect(screen.getByText("Computer Science and Engineering")).toBeInTheDocument();
  });

  it("says when nobody has been appointed, rather than showing nothing", async () => {
    fetchMyDepartment.mockResolvedValue({
      department_id: "d1",
      department_name: "Physics",
      user_id: null,
      full_name: null,
      registration_number: null,
      designation: null,
      email: null,
    });
    renderCard();

    expect(
      await screen.findByText(/no research coordinator has been appointed/i),
    ).toBeInTheDocument();
  });

  it("renders nothing for somebody with no department", async () => {
    fetchMyDepartment.mockResolvedValue(null);
    // Awaited on purpose: asserting emptiness straight away would only prove
    // the card renders nothing while still loading, which is not the claim.
    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <DepartmentCoordinatorCard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(fetchMyDepartment).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
