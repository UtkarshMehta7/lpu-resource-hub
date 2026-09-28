import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { describeNotification } from "@/features/notifications/describe";
import type { AppNotification } from "@/features/notifications/api";

import { AtRiskBoardPage } from "./AtRiskBoardPage";
import { MilestoneSection } from "./MilestoneList";
import { MilestoneTimeline } from "./MilestoneTimeline";
import { describeDue } from "./labels";
import type { AtRiskProject, Milestone } from "./types";

const fetchMilestones = vi.fn<() => Promise<Milestone[]>>();
const changeMilestoneStatus = vi.fn<() => Promise<Milestone>>();
const fetchAtRiskProjects = vi.fn<() => Promise<AtRiskProject[]>>();

vi.mock("./api", () => ({
  milestoneQueryKey: (projectId: string) => ["milestones", projectId],
  fetchMilestones: () => fetchMilestones(),
  changeMilestoneStatus: () => changeMilestoneStatus(),
  deleteMilestone: vi.fn(),
  removeDependency: vi.fn(),
  addDependency: vi.fn(),
  createMilestone: vi.fn(),
  updateMilestone: vi.fn(),
  fetchAtRiskProjects: () => fetchAtRiskProjects(),
  fetchMyMilestones: vi.fn(),
}));

function milestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: "m1",
    project_id: "p1",
    title: "Survey existing sensors",
    description: null,
    due_date: "2026-04-14",
    status: "pending",
    position: 1,
    completed_at: null,
    completed_by: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    risk: "on_track",
    days_until_due: 30,
    depends_on: [],
    blocked_by: [],
    ...overrides,
  };
}

function renderWith(element: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMilestones.mockReset();
  changeMilestoneStatus.mockReset();
  fetchAtRiskProjects.mockReset();
});

describe("MilestoneSection", () => {
  it("says what to do when there is no plan yet, to whoever can make one", async () => {
    fetchMilestones.mockResolvedValue([]);
    renderWith(<MilestoneSection projectId="p1" canPlan canMove />);
    expect(await screen.findByText(/add the first one/i)).toBeInTheDocument();
  });

  it("does not invite somebody who cannot plan to add anything", async () => {
    fetchMilestones.mockResolvedValue([]);
    renderWith(<MilestoneSection projectId="p1" canPlan={false} canMove={false} />);
    expect(await screen.findByText(/no milestones yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add milestone" })).not.toBeInTheDocument();
  });

  it("shows the risk of each milestone in words, not only colour", async () => {
    fetchMilestones.mockResolvedValue([
      milestone({ id: "a", title: "Late one", risk: "overdue", days_until_due: -3 }),
      milestone({ id: "b", title: "Soon one", risk: "at_risk", days_until_due: 2 }),
    ]);
    renderWith(<MilestoneSection projectId="p1" canPlan canMove />);

    // Scoped to the list: the timeline legend names the same risks, and both
    // are rendered -- the timeline is hidden by CSS, which jsdom does not apply.
    const plan = await screen.findByRole("list", { name: "Milestone plan" });
    expect(within(plan).getByText("Overdue")).toBeInTheDocument();
    expect(within(plan).getByText("Due soon")).toBeInTheDocument();
    expect(within(plan).getByText(/3 days late/)).toBeInTheDocument();
  });

  it("names what is blocking a milestone rather than only marking it blocked", async () => {
    fetchMilestones.mockResolvedValue([
      milestone({
        id: "b",
        title: "Field trial",
        risk: "blocked",
        depends_on: [
          { id: "a", title: "Build prototype", due_date: "2026-03-01", status: "pending" },
        ],
        blocked_by: [
          { id: "a", title: "Build prototype", due_date: "2026-03-01", status: "pending" },
        ],
      }),
    ]);
    renderWith(<MilestoneSection projectId="p1" canPlan canMove />);

    const plan = await screen.findByRole("list", { name: "Milestone plan" });
    expect(within(plan).getByText("Blocked")).toBeInTheDocument();
    expect(within(plan).getByText(/waits on/)).toBeInTheDocument();
    expect(within(plan).getByText("Build prototype")).toBeInTheDocument();
  });

  it("offers a member the moves they may make and none of the ones they may not", async () => {
    fetchMilestones.mockResolvedValue([milestone()]);
    renderWith(<MilestoneSection projectId="p1" canPlan={false} canMove />);

    expect(await screen.findByRole("button", { name: "Mark done" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
    // Cancelling and deleting are the owner's, and the backend enforces it.
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("gives an onlooker no buttons at all", async () => {
    fetchMilestones.mockResolvedValue([milestone()]);
    renderWith(<MilestoneSection projectId="p1" canPlan={false} canMove={false} />);

    const plan = await screen.findByRole("list", { name: "Milestone plan" });
    expect(within(plan).getByText("Survey existing sensors")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark done" })).not.toBeInTheDocument();
  });

  it("marks a milestone done through the API", async () => {
    const user = userEvent.setup();
    fetchMilestones.mockResolvedValue([milestone()]);
    changeMilestoneStatus.mockResolvedValue(milestone({ status: "done", risk: "none" }));
    renderWith(<MilestoneSection projectId="p1" canPlan canMove />);

    await user.click(await screen.findByRole("button", { name: "Mark done" }));
    expect(changeMilestoneStatus).toHaveBeenCalled();
  });

  it("offers reopening only once something is done", async () => {
    fetchMilestones.mockResolvedValue([
      milestone({ status: "done", risk: "none", completed_at: "2026-02-01T00:00:00Z" }),
    ]);
    renderWith(<MilestoneSection projectId="p1" canPlan canMove />);

    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark done" })).not.toBeInTheDocument();
  });
});

describe("MilestoneTimeline", () => {
  const NOW = new Date("2026-03-15T00:00:00Z").getTime();

  it("draws one bar per milestone and labels itself for a screen reader", () => {
    renderWith(
      <MilestoneTimeline
        now={NOW}
        milestones={[
          milestone({ id: "a", title: "One", due_date: "2026-03-01" }),
          milestone({ id: "b", title: "Two", due_date: "2026-04-01" }),
        ]}
      />,
    );
    const figure = screen.getByLabelText("Milestone timeline");
    expect(within(figure).getByRole("img", { name: /2 milestones/ })).toBeInTheDocument();
    expect(within(figure).getByText("One")).toBeInTheDocument();
    expect(within(figure).getByText("Two")).toBeInTheDocument();
  });

  it("carries a legend, so the bars are never colour alone", () => {
    renderWith(<MilestoneTimeline now={NOW} milestones={[milestone()]} />);
    const figure = screen.getByLabelText("Milestone timeline");
    expect(within(figure).getByText("Overdue")).toBeInTheDocument();
    expect(within(figure).getByText("On track")).toBeInTheDocument();
  });

  it("renders nothing rather than an empty frame when there is no plan", () => {
    renderWith(<MilestoneTimeline now={NOW} milestones={[]} />);
    expect(screen.queryByLabelText("Milestone timeline")).not.toBeInTheDocument();
  });
});

describe("AtRiskBoardPage", () => {
  it("says so plainly when nothing is slipping", async () => {
    fetchAtRiskProjects.mockResolvedValue([]);
    renderWith(<AtRiskBoardPage />);
    expect(await screen.findByText(/nothing is slipping/i)).toBeInTheDocument();
  });

  it("counts each kind of trouble per project", async () => {
    fetchAtRiskProjects.mockResolvedValue([
      {
        project_id: "p1",
        title: "Low-cost soil sensors",
        owner_id: "u1",
        owner_name: "A. Sharma",
        owner_registration_number: "12400942",
        department_id: null,
        overdue_count: 2,
        at_risk_count: 1,
        blocked_count: 0,
        milestones: [
          {
            id: "m1",
            title: "Field trial",
            due_date: "2026-02-01",
            status: "pending",
            risk: "overdue",
            days_until_due: -9,
          },
        ],
      },
    ]);
    renderWith(<AtRiskBoardPage />);

    expect(await screen.findByText("Low-cost soil sensors")).toBeInTheDocument();
    expect(screen.getByText("2 overdue")).toBeInTheDocument();
    expect(screen.getByText("1 due soon")).toBeInTheDocument();
    // A kind with no instances is not shown as a zero.
    expect(screen.queryByText(/blocked$/)).not.toBeInTheDocument();
    expect(screen.getByText("12400942")).toBeInTheDocument();
  });
});

describe("milestone notifications", () => {
  function notification(
    type: AppNotification["notification_type"],
    payload: Record<string, unknown>,
  ): AppNotification {
    return {
      id: "n1",
      notification_type: type,
      payload,
      read_at: null,
      created_at: "2026-03-01T00:00:00Z",
    };
  }

  it("says a due milestone in readable words and links to its project", () => {
    const line = describeNotification(
      notification("milestone_due", {
        title: "Field trial",
        project_id: "p1",
        project_title: "Soil sensors",
        days_left: 7,
      }),
    );
    expect(line.text).toBe("“Field trial” is due in 7 days");
    expect(line.to).toBe("/projects/p1");
    expect(line.detail).toBe("Soil sensors");
  });

  it("says tomorrow rather than in 1 days", () => {
    const line = describeNotification(
      notification("milestone_due", { title: "Field trial", project_id: "p1", days_left: 1 }),
    );
    expect(line.text).toBe("“Field trial” is due tomorrow");
  });

  it("describes an overdue milestone", () => {
    const line = describeNotification(
      notification("milestone_overdue", { title: "Final report", project_id: "p2" }),
    );
    expect(line.text).toBe("“Final report” is past its due date");
    expect(line.to).toBe("/projects/p2");
  });
});

describe("describeDue", () => {
  it("reads naturally either side of the date", () => {
    expect(describeDue(0)).toBe("due today");
    expect(describeDue(1)).toBe("due tomorrow");
    expect(describeDue(-1)).toBe("1 day late");
    expect(describeDue(-5)).toBe("5 days late");
    expect(describeDue(9)).toBe("in 9 days");
  });
});
