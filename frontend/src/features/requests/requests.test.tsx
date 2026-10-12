import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { navigationFor, searchNavigation } from "@/components/layout/navigation";
import type { Role } from "@/features/auth/types";

import type * as ApiModule from "./api";
import type * as RouterModule from "react-router-dom";
import type { PersonalRequest } from "./api";
import { RequestDetailPage } from "./RequestDetailPage";
import { RequestFormPage } from "./RequestFormPage";

const {
  fetchRequest,
  fetchRecipients,
  changeRequestStatus,
  submitRequest,
  downloadRequestAttachment,
} = vi.hoisted(() => ({
  fetchRequest: vi.fn(),
  fetchRecipients: vi.fn(),
  changeRequestStatus: vi.fn(),
  submitRequest: vi.fn(),
  downloadRequestAttachment: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  fetchRequest,
  fetchRecipients,
  changeRequestStatus,
  submitRequest,
  downloadRequestAttachment,
}));
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof RouterModule>();
  return { ...actual, useParams: () => ({ requestId: "r1" }), useNavigate: () => vi.fn() };
});

function request(overrides: Partial<PersonalRequest> = {}): PersonalRequest {
  return {
    id: "r1",
    subject: "Approval needed for my project submission",
    body: "Please could you look at this before Friday.",
    category: "academic",
    status: "submitted",
    sender_id: "u-student",
    sender_name: "Demo Student 01",
    sender_registration_number: "12500301",
    sender_role: "student",
    recipient_id: "u-faculty",
    recipient_name: "Demo Faculty 01",
    recipient_role: "faculty",
    resolution_note: null,
    decided_at: null,
    attachments: [],
    next_statuses: [],
    viewer_is_sender: false,
    created_at: "2026-10-10T09:00:00Z",
    updated_at: "2026-10-10T09:00:00Z",
    ...overrides,
  };
}

function renderWith(node: React.ReactNode) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchRecipients.mockResolvedValue([]);
});

describe("reading a request", () => {
  it("offers only the moves the server says this reader has", async () => {
    // next_statuses is computed per reader, so the page never offers a step
    // the service would refuse. There is no local transition table.
    fetchRequest.mockResolvedValue(
      request({ next_statuses: ["under_review", "resolved", "declined"] }),
    );

    renderWith(<RequestDetailPage />);

    expect(await screen.findByRole("button", { name: "Take it up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark resolved" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
  });

  it("gives the sender only what a sender has", async () => {
    fetchRequest.mockResolvedValue(
      request({ viewer_is_sender: true, next_statuses: ["withdrawn"] }),
    );

    renderWith(<RequestDetailPage />);

    expect(await screen.findByRole("button", { name: "Withdraw" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark resolved" })).not.toBeInTheDocument();
  });

  it("offers nothing once it is finished", async () => {
    fetchRequest.mockResolvedValue(
      request({ status: "resolved", next_statuses: [], resolution_note: "Signed." }),
    );

    renderWith(<RequestDetailPage />);

    expect(await screen.findByText("Signed.")).toBeInTheDocument();
    expect(screen.queryByText("What happens next")).not.toBeInTheDocument();
  });

  it("asks for a reason before declining, and not before anything else", async () => {
    fetchRequest.mockResolvedValue(request({ next_statuses: ["under_review", "declined"] }));
    changeRequestStatus.mockResolvedValue(request({ status: "under_review" }));

    renderWith(<RequestDetailPage />);

    // Taking it up goes straight through.
    await userEvent.click(await screen.findByRole("button", { name: "Take it up" }));
    await waitFor(() =>
      expect(changeRequestStatus).toHaveBeenCalledWith("r1", "under_review", undefined),
    );

    // Declining stops and asks.
    await userEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(screen.getByLabelText("Why are you declining?")).toBeInTheDocument();
  });

  it("will not send a decline with an empty reason", async () => {
    fetchRequest.mockResolvedValue(request({ next_statuses: ["declined"] }));

    renderWith(<RequestDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));

    const confirm = screen.getByRole("button", { name: "Decline the request" });
    expect(confirm).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Why are you declining?"), "Not my form to sign.");
    expect(confirm).toBeEnabled();
  });

  it("names why it was declined, so the reason is never lost", async () => {
    fetchRequest.mockResolvedValue(
      request({ status: "declined", resolution_note: "Not my form to sign." }),
    );

    renderWith(<RequestDetailPage />);

    expect(await screen.findByText("Why it was declined")).toBeInTheDocument();
    expect(screen.getByText("Not my form to sign.")).toBeInTheDocument();
  });

  it("downloads an attachment through the API rather than a plain link", async () => {
    const attachment = {
      id: "f1",
      filename: "form.pdf",
      content_type: "application/pdf",
      byte_size: 2048,
    };
    fetchRequest.mockResolvedValue(request({ attachments: [attachment] }));

    renderWith(<RequestDetailPage />);
    await userEvent.click(await screen.findByRole("button", { name: /form\.pdf/ }));

    expect(downloadRequestAttachment).toHaveBeenCalledWith("r1", attachment);
  });

  it("says plainly when a request is not yours to read", async () => {
    fetchRequest.mockRejectedValue(new Error("404"));

    renderWith(<RequestDetailPage />);

    expect(await screen.findByText("Request not found")).toBeInTheDocument();
  });
});

describe("making a request", () => {
  it("offers only the people the server says you may address", async () => {
    fetchRecipients.mockResolvedValue([
      {
        id: "u-faculty",
        full_name: "Demo Faculty 01",
        registration_number: "12500201",
        role: "faculty",
        department_id: "d1",
        department_name: "Information Technology",
      },
    ]);

    renderWith(<RequestFormPage />);

    const picker = await screen.findByLabelText("Who is this for?");
    expect(picker).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Demo Faculty 01/ })).toBeInTheDocument();
    // No free-text recipient: a request goes to one named person above you.
    expect(screen.queryByRole("textbox", { name: /who/i })).not.toBeInTheDocument();
  });

  it("says so plainly when there is nobody above you", async () => {
    // An administrator is at the top of the chain. An empty list is a real
    // answer, not a failure.
    fetchRecipients.mockResolvedValue([]);

    renderWith(<RequestFormPage />);

    expect(
      await screen.findByText("There is nobody for you to put a request to"),
    ).toBeInTheDocument();
  });
});

describe("reachability", () => {
  it("lets every role read what was put to them", () => {
    for (const role of [
      "student",
      "faculty",
      "research_coordinator",
      "facility_custodian",
      "dean_of_research",
      "admin",
    ] as Role[]) {
      expect(navigationFor(role).map((i) => i.to)).toContain("/me/requests");
    }
  });

  it("offers making one to everybody but an administrator", () => {
    for (const role of [
      "student",
      "faculty",
      "facility_custodian",
      "research_coordinator",
      "dean_of_research",
    ] as Role[]) {
      expect(navigationFor(role).map((i) => i.to)).toContain("/requests/new");
    }
    expect(navigationFor("admin").map((i) => i.to)).not.toContain("/requests/new");
  });

  it("offers the inbox only to roles somebody can address", () => {
    for (const role of ["faculty", "research_coordinator", "dean_of_research", "admin"] as Role[]) {
      expect(navigationFor(role).map((i) => i.to)).toContain("/requests/inbox");
    }
    // Nobody may address a student or a custodian, so an inbox would always
    // be empty.
    for (const role of ["student", "facility_custodian"] as Role[]) {
      expect(navigationFor(role).map((i) => i.to)).not.toContain("/requests/inbox");
    }
  });

  it("does not leave two unrelated things called the same word", () => {
    // "Requests" was the collaborations page until personal requests
    // arrived, and one menu with two of them is unreadable.
    const labels = navigationFor("faculty").map((i) => i.label);

    expect(labels.filter((l) => l === "Requests")).toHaveLength(0);
    expect(labels).toContain("Collaboration requests");
    expect(labels).toContain("My requests");
  });

  it("is findable by the words people type", () => {
    const student = navigationFor("student");

    for (const query of ["request", "ask", "escalate", "approval"]) {
      expect(searchNavigation(student, query).map((i) => i.to)).toContain("/requests/new");
    }
  });
});
