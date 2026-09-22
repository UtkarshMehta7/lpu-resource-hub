import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { RequestCollaborationButton } from "./RequestCollaborationButton";

const { sendMock, authState } = vi.hoisted(() => ({
  sendMock: vi.fn(),
  authState: {
    user: { id: "me", full_name: "Me", role: "student" } as { id: string; role: string } | null,
  },
}));

vi.mock("./api", () => ({ sendCollaborationRequest: sendMock }));
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
    <QueryClientProvider client={new QueryClient()}>
      <RequestCollaborationButton
        recipientId={recipientId}
        recipientName="Dr. Demo"
        projectId="p1"
      />
    </QueryClientProvider>,
  );
}

describe("RequestCollaborationButton", () => {
  beforeEach(() => {
    sendMock.mockReset();
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
    expect(await screen.findByRole("button", { name: /request sent/i })).toBeDisabled();
  });
});
