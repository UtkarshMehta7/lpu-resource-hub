import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadPage } from "./ThreadPage";
import type { Conversation, Message } from "./api";

const { fetchConversation, fetchMessages, sendMessage, markConversationRead, useAuthMock } =
  vi.hoisted(() => ({
    fetchConversation: vi.fn(),
    fetchMessages: vi.fn(),
    sendMessage: vi.fn(),
    markConversationRead: vi.fn(),
    useAuthMock: vi.fn(),
  }));

vi.mock("./api", () => ({
  fetchConversation,
  fetchMessages,
  sendMessage,
  markConversationRead,
}));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));
vi.mock("@/features/reports/ReportButton", () => ({
  ReportButton: () => <button type="button">Report</button>,
}));

const CONVERSATION: Conversation = {
  id: "c1",
  subject_kind: "collaboration",
  subject_id: "r1",
  title: "Demo Faculty 07",
  participants: [
    {
      user_id: "u-me",
      full_name: "Demo Student 01",
      registration_number: "12400942",
      role: "student",
    },
    {
      user_id: "u-them",
      full_name: "Demo Faculty 07",
      registration_number: "DEMOFACULTY07",
      role: "faculty",
    },
  ],
  unread_count: 0,
  last_message_at: "2026-09-24T10:00:00Z",
  preview: "Hello",
  created_at: "2026-09-24T09:00:00Z",
};

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: "m1",
    conversation_id: "c1",
    sender_id: "u-them",
    sender_name: "Demo Faculty 07",
    sender_registration_number: "DEMOFACULTY07",
    body: "Welcome aboard",
    hidden: false,
    created_at: "2026-09-24T10:00:00Z",
    ...overrides,
  };
}

function renderThread() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/messages/c1"]}>
        <Routes>
          <Route path="/messages/:conversationId" element={<ThreadPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "u-me", role: "student" } });
  fetchConversation.mockResolvedValue(CONVERSATION);
  fetchMessages.mockResolvedValue({ items: [message()], next_after: "cursor-1" });
  sendMessage.mockResolvedValue(message({ id: "m2", sender_id: "u-me", body: "Thanks" }));
  markConversationRead.mockResolvedValue(undefined);
});

describe("ThreadPage", () => {
  it("shows the other person with their UID and the messages", async () => {
    renderThread();

    expect(await screen.findByText("Welcome aboard")).toBeInTheDocument();
    expect(screen.getAllByText("DEMOFACULTY07").length).toBeGreaterThan(0);
  });

  it("marks the thread read when it is opened", async () => {
    renderThread();

    await waitFor(() => expect(markConversationRead).toHaveBeenCalledWith("c1"));
  });

  it("sends with the button", async () => {
    const user = userEvent.setup();
    renderThread();

    await screen.findByText("Welcome aboard");
    await user.type(screen.getByLabelText("Message"), "Thanks");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalledWith("c1", "Thanks"));
  });

  it("sends on Enter and keeps Shift+Enter for a new line", async () => {
    const user = userEvent.setup();
    renderThread();

    await screen.findByText("Welcome aboard");
    const box = screen.getByLabelText("Message");

    await user.type(box, "line one{Shift>}{Enter}{/Shift}line two");
    expect(sendMessage).not.toHaveBeenCalled();

    await user.type(box, "{Enter}");
    await waitFor(() => expect(sendMessage).toHaveBeenCalledWith("c1", "line one\nline two"));
  });

  it("refuses to send an empty message", async () => {
    const user = userEvent.setup();
    renderThread();

    await screen.findByText("Welcome aboard");
    await user.type(screen.getByLabelText("Message"), "   ");
    await user.type(screen.getByLabelText("Message"), "{Enter}");

    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("shows a hidden message as removed, in its place", async () => {
    fetchMessages.mockResolvedValue({
      items: [message(), message({ id: "m9", body: null, hidden: true })],
      next_after: "cursor-2",
    });
    renderThread();

    expect(await screen.findByText(/removed by a moderator/i)).toBeInTheDocument();
    // Still two bubbles: hiding leaves no hole.
    expect(screen.getByText("Welcome aboard")).toBeInTheDocument();
  });

  it("says who can see an empty thread", async () => {
    fetchMessages.mockResolvedValue({ items: [], next_after: null });
    renderThread();

    expect(await screen.findByText(/only the two of you can see this thread/i)).toBeInTheDocument();
  });

  it("surfaces the reason a send was refused", async () => {
    const user = userEvent.setup();
    sendMessage.mockRejectedValue(new Error("nope"));
    renderThread();

    await screen.findByText("Welcome aboard");
    await user.type(screen.getByLabelText("Message"), "Hi");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("explains a thread it cannot load rather than showing an empty page", async () => {
    fetchConversation.mockRejectedValue(new Error("404"));
    renderThread();

    expect(await screen.findByText(/isn't available/i)).toBeInTheDocument();
  });
});
