import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DepartmentComparison } from "./DepartmentComparison";

const { fetchDepartmentComparison } = vi.hoisted(() => ({
  fetchDepartmentComparison: vi.fn(),
}));

vi.mock("./api", () => ({ fetchDepartmentComparison }));

const ROWS = [
  {
    department_id: "d1",
    department_name: "Architecture",
    school_name: "School of Design",
    researchers: 4,
    students: 20,
    projects_active: 1,
    publications: 2,
    milestones_overdue: 0,
    milestones_at_risk: 0,
    verification_pending: 1,
  },
  {
    department_id: "d2",
    department_name: "Computer Science and Engineering",
    school_name: "School of Computer Science",
    researchers: 12,
    students: 60,
    projects_active: 5,
    publications: 40,
    milestones_overdue: 3,
    milestones_at_risk: 2,
    verification_pending: 0,
  },
];

function renderIt() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DepartmentComparison />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDepartmentComparison.mockResolvedValue(ROWS);
});

describe("DepartmentComparison", () => {
  it("shows each department's figures side by side", async () => {
    renderIt();

    const row = (await screen.findByRole("row", { name: /Computer Science and Engineering/ }))
      .textContent;
    expect(row).toContain("12");
    expect(row).toContain("40");
    // One blended institutional total is exactly what this replaces.
    expect(await screen.findByRole("row", { name: /Architecture/ })).toBeInTheDocument();
  });

  it("puts what needs attention first, not alphabetical order", async () => {
    renderIt();
    await screen.findByText("Architecture");

    const names = screen
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent?.split("School")[0]?.trim());

    // Computer Science has 3 overdue milestones; Architecture has none.
    expect(names[0]).toBe("Computer Science and Engineering");
  });

  it("names the school under each department", async () => {
    renderIt();

    const row = await screen.findByRole("row", { name: /Architecture/ });
    expect(within(row).getByText("School of Design")).toBeInTheDocument();
  });

  it("says so when there is nothing to compare", async () => {
    fetchDepartmentComparison.mockResolvedValue([]);
    renderIt();

    expect(await screen.findByText("No departments to compare yet.")).toBeInTheDocument();
  });
});
