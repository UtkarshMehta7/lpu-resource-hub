import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ThreadPage } from "./ThreadPage";
import type { Conversation, Message } from "./api";

const {
  fetchConversation,
  fetchMessages,
  sendMessage,
  sendAttachment,
  downloadAttachment,
  markConversationRead,
  useAuthMock,
} = vi.hoisted(() => ({
  fetchConversation: vi.fn(),
  fetchMessages: vi.fn(),
  sendMessage: vi.fn(),
  sendAttachment: vi.fn(),
  downloadAttachment: vi.fn(),
  markConversationRead: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", () => ({
  fetchConversation,
  fetchMessages,
  sendMessage,
  sendAttachment,
  downloadAttachment,
  markConversationRead,
  // Values, not functions: the component imports these to drive the picker
  // and to refuse an oversized file before uploading it.
  ACCEPTED_UPLOAD_TYPES: "application/pdf,image/png",
  MAX_UPLOAD_BYTES: 5 * 1024 * 1024,
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
  open: true,
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
    attachments: [],
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
  sendAttachment.mockResolvedValue(message({ id: "m3", sender_id: "u-me", body: "" }));
  downloadAttachment.mockResolvedValue(undefined);
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

  it("says a finished collaboration is read-only instead of offering a composer", async () => {
    fetchConversation.mockResolvedValue({ ...CONVERSATION, open: false });
    renderThread();

    expect(await screen.findByText(/read-only/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Message")).toBeNull();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });

  it("explains a thread it cannot load rather than showing an empty page", async () => {
    fetchConversation.mockRejectedValue(new Error("404"));
    renderThread();

    expect(await screen.findByText(/isn't available/i)).toBeInTheDocument();
  });
});

describe("sharing a file in a thread", () => {
  const pdf = () =>
    new File([new Uint8Array([37, 80, 68, 70])], "survey.pdf", {
      type: "application/pdf",
    });

  it("sends the chosen file with the draft as its caption", async () => {
    renderThread();
    await screen.findByText("Welcome aboard");

    await userEvent.upload(screen.getByLabelText("Attach a file", { exact: true }), pdf());
    // Named before it is sent, so nobody uploads the wrong file.
    expect(await screen.findByText("survey.pdf")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Message", { exact: true }), "Last year's survey");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(sendAttachment).toHaveBeenCalledTimes(1));
    expect(sendAttachment.mock.calls[0]?.[2]).toBe("Last year's survey");
    // One send, not two: the caption rides with the file.
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("sends a file with no caption at all", async () => {
    renderThread();
    await screen.findByText("Welcome aboard");

    await userEvent.upload(screen.getByLabelText("Attach a file", { exact: true }), pdf());
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(sendAttachment).toHaveBeenCalledTimes(1));
    expect(sendAttachment.mock.calls[0]?.[2]).toBe("");
  });

  it("refuses a file over the limit before uploading it", async () => {
    renderThread();
    await screen.findByText("Welcome aboard");

    const huge = new File([new Uint8Array(6 * 1024 * 1024)], "huge.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(screen.getByLabelText("Attach a file", { exact: true }), huge);

    expect(await screen.findByRole("alert")).toHaveTextContent(/larger than 5 MB/i);
    // The point of checking here: the server would refuse it anyway, but not
    // before somebody spent six megabytes of mobile data on it.
    expect(sendAttachment).not.toHaveBeenCalled();
  });

  it("lets a chosen file be removed again", async () => {
    renderThread();
    await screen.findByText("Welcome aboard");

    await userEvent.upload(screen.getByLabelText("Attach a file", { exact: true }), pdf());
    await userEvent.click(await screen.findByRole("button", { name: "Remove" }));

    expect(screen.queryByText("survey.pdf")).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("offers a received file for download, with its size", async () => {
    fetchMessages.mockResolvedValue({
      items: [
        message({
          body: "Here it is",
          attachments: [
            {
              id: "a1",
              filename: "survey.pdf",
              content_type: "application/pdf",
              byte_size: 2048,
            },
          ],
        }),
      ],
      next_after: "cursor-1",
    });
    renderThread();

    const file = await screen.findByRole("button", { name: /survey\.pdf/ });
    expect(file).toHaveTextContent("2 KB");

    await userEvent.click(file);

    await waitFor(() => expect(downloadAttachment).toHaveBeenCalledTimes(1));
    expect(downloadAttachment.mock.calls[0]?.[1]).toMatchObject({ filename: "survey.pdf" });
  });

  it("says so when a download fails instead of doing nothing", async () => {
    downloadAttachment.mockRejectedValue(new Error("network"));
    fetchMessages.mockResolvedValue({
      items: [
        message({
          attachments: [
            { id: "a1", filename: "survey.pdf", content_type: "application/pdf", byte_size: 10 },
          ],
        }),
      ],
      next_after: "cursor-1",
    });
    renderThread();

    await userEvent.click(await screen.findByRole("button", { name: /survey\.pdf/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not download/i);
  });

  it("withholds the file of a hidden message, not just its text", async () => {
    fetchMessages.mockResolvedValue({
      items: [
        message({
          body: null,
          hidden: true,
          attachments: [
            { id: "a1", filename: "survey.pdf", content_type: "application/pdf", byte_size: 10 },
          ],
        }),
      ],
      next_after: "cursor-1",
    });
    renderThread();

    expect(await screen.findByText(/removed by a moderator/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /survey\.pdf/ })).toBeNull();
  });
});
