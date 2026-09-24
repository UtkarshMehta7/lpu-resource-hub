import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { MemoryRouter } from "react-router-dom";

import { RequestCollaborationButton } from "./RequestCollaborationButton";

const { sendMock, stateMock, respondMock, authState } = vi.hoisted(() => ({
  sendMock: vi.fn(),
  stateMock: vi.fn(),
  respondMock: vi.fn(),
  authState: {
    user: { id: "me", full_name: "Me", role: "student" } as { id: string; role: string } | null,
  },
}));

vi.mock("./api", () => ({
  sendCollaborationRequest: sendMock,
  fetchCollaborationState: stateMock,
  respondToCollaboration: respondMock,
}));
vi.mock("@/features/auth/authContext", () => ({ useAuth: () => authState }));

beforeAll(() => {
  // jsdom doesn't implement <dialog>.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
  };
});

function renderButton(recipientId = "them") {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <RequestCollaborationButton
          recipientId={recipientId}
          recipientName="Dr. Demo"
          projectId="p1"
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RequestCollaborationButton", () => {
  beforeEach(() => {
    sendMock.mockReset();
    stateMock.mockReset();
    respondMock.mockReset();
    // Nothing between them yet, unless a test says otherwise.
    stateMock.mockResolvedValue({
      state: "none",
      request_id: null,
      i_sent_it: null,
      conversation_id: null,
    });
    respondMock.mockResolvedValue({});
    authState.user = { id: "me", role: "student" };
  });

  it("is hidden for admins and on your own page", () => {
    authState.user = { id: "me", role: "admin" };
    renderButton();
    expect(screen.queryByRole("button", { name: /request collaboration/i })).toBeNull();

    authState.user = { id: "them", role: "faculty" };
    renderButton("them");
    expect(screen.queryByRole("button", { name: /request collaboration/i })).toBeNull();
  });

  it("requires a message, then sends it with the project", async () => {
    const user = userEvent.setup();
    sendMock.mockResolvedValue({});
    renderButton();

    await user.click(screen.getByRole("button", { name: /request collaboration/i }));
    await user.click(screen.getByRole("button", { name: /send request/i, hidden: true }));
    expect(await screen.findByText(/write a short message/i)).toBeInTheDocument();
    expect(sendMock).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/message/i), "  Let's work on soil sensors ");
    await user.click(screen.getByRole("button", { name: /send request/i, hidden: true }));

    await vi.waitFor(() =>
      expect(sendMock).toHaveBeenCalledWith({
        recipient_id: "them",
        project_id: "p1",
        message: "Let's work on soil sensors",
      }),
    );
    // It used to say "Request sent" and go dead. Saying the request is
    // pending, and offering to take it back, is the more useful truth.
    expect(await screen.findByText(/request pending/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel request/i })).toBeInTheDocument();
  });

  it("offers the conversation, not another request, once they collaborate", async () => {
    stateMock.mockResolvedValue({
      state: "active",
      request_id: null,
      i_sent_it: null,
      conversation_id: "c1",
    });
    renderButton();

    expect(await screen.findByRole("link", { name: /open conversation/i })).toHaveAttribute(
      "href",
      "/messages/c1",
    );
    expect(screen.queryByRole("button", { name: /request collaboration/i })).toBeNull();
  });

  it("lets the sender cancel while a request is pending", async () => {
    const user = userEvent.setup();
    stateMock.mockResolvedValue({
      state: "requested",
      request_id: "r1",
      i_sent_it: true,
      conversation_id: null,
    });
    renderButton();

    await user.click(await screen.findByRole("button", { name: /cancel request/i }));

    expect(respondMock).toHaveBeenCalledWith("r1", "cancel");
  });

  it("asks the recipient to answer, rather than to request back", async () => {
    const user = userEvent.setup();
    stateMock.mockResolvedValue({
      state: "requested",
      request_id: "r1",
      i_sent_it: false,
      conversation_id: null,
    });
    renderButton();

    await user.click(await screen.findByRole("button", { name: "Accept" }));

    expect(respondMock).toHaveBeenCalledWith("r1", "accept");
    expect(screen.queryByRole("button", { name: /request collaboration/i })).toBeNull();
  });

  it("invites them to collaborate again once it has ended", async () => {
    stateMock.mockResolvedValue({
      state: "ended",
      request_id: null,
      i_sent_it: null,
      conversation_id: "c1",
    });
    renderButton();

    expect(await screen.findByRole("button", { name: /collaborate again/i })).toBeInTheDocument();
  });
});
