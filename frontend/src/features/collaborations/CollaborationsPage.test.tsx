import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CollaborationsPage } from "./CollaborationsPage";
import type * as collaborationsApi from "./api";
import type { CollaborationRequest } from "./api";

const { fetchMyCollaborations, respondToCollaboration } = vi.hoisted(() => ({
  fetchMyCollaborations: vi.fn(),
  respondToCollaboration: vi.fn(),
}));

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof collaborationsApi>("./api");
  return { ...actual, fetchMyCollaborations, respondToCollaboration };
});

function request(overrides: Partial<CollaborationRequest> = {}): CollaborationRequest {
  return {
    id: "r1",
    sender: {
      id: "u-me",
      full_name: "Demo Student 01",
      registration_number: "12400942",
      role: "student",
    },
    recipient: {
      id: "u-them",
      full_name: "Demo Faculty 07",
      registration_number: "DEMOFACULTY07",
      role: "faculty",
    },
    project_id: null,
    project_title: null,
    message: "Could we collaborate on the field trials?",
    status: "pending",
    responded_at: null,
    created_at: "2026-09-24T10:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CollaborationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchMyCollaborations.mockResolvedValue([request()]);
  respondToCollaboration.mockResolvedValue(request({ status: "ended" }));
});

describe("CollaborationsPage", () => {
  it("lets either party end an accepted collaboration", async () => {
    const user = userEvent.setup();
    fetchMyCollaborations.mockResolvedValue([request({ status: "accepted" })]);
    renderPage();

    await user.click(await screen.findByRole("button", { name: /end collaboration/i }));

    await waitFor(() => expect(respondToCollaboration).toHaveBeenCalledWith("r1", "end"));
  });

  it("offers a way into the conversation while it is running", async () => {
    fetchMyCollaborations.mockResolvedValue([request({ status: "accepted" })]);
    renderPage();

    expect(await screen.findByRole("link", { name: /open conversation/i })).toBeInTheDocument();
  });

  it("does not offer to end one that has already ended", async () => {
    fetchMyCollaborations.mockResolvedValue([request({ status: "ended" })]);
    renderPage();

    expect(await screen.findByText(/this collaboration has ended/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /end collaboration/i })).toBeNull();
  });

  it("still offers accept and decline while it is pending", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /end collaboration/i })).toBeNull();
  });

  it("surfaces the reason the server refused", async () => {
    const user = userEvent.setup();
    fetchMyCollaborations.mockResolvedValue([request({ status: "accepted" })]);
    respondToCollaboration.mockRejectedValue(new Error("nope"));
    renderPage();

    await user.click(await screen.findByRole("button", { name: /end collaboration/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
