import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConversationsPage } from "./ConversationsPage";
import type { Conversation } from "./api";

const { fetchConversations, useAuthMock } = vi.hoisted(() => ({
  fetchConversations: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", () => ({ fetchConversations }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
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
    preview: "Welcome aboard",
    created_at: "2026-09-24T09:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ConversationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "u-me", role: "student" } });
  fetchConversations.mockResolvedValue([conversation()]);
});

describe("ConversationsPage", () => {
  it("names the other person, with their UID and a preview", async () => {
    renderPage();

    expect(await screen.findByText("Demo Faculty 07")).toBeInTheDocument();
    expect(screen.getByText("DEMOFACULTY07")).toBeInTheDocument();
    expect(screen.getByText("Welcome aboard")).toBeInTheDocument();
  });

  it("shows the unread count", async () => {
    fetchConversations.mockResolvedValue([conversation({ unread_count: 3 })]);
    renderPage();

    expect(await screen.findByLabelText("3 unread")).toBeInTheDocument();
  });

  it("marks a project thread as the team's", async () => {
    fetchConversations.mockResolvedValue([
      conversation({ subject_kind: "project", title: "Soil sensors" }),
    ]);
    renderPage();

    expect(await screen.findByText("Project team")).toBeInTheDocument();
    expect(screen.getByText("Soil sensors")).toBeInTheDocument();
  });

  it("invites a first message on a thread with none", async () => {
    fetchConversations.mockResolvedValue([conversation({ preview: null })]);
    renderPage();

    expect(await screen.findByText(/say hello/i)).toBeInTheDocument();
  });

  it("explains an empty list instead of showing nothing", async () => {
    fetchConversations.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
  });

  it("reports a failure to load", async () => {
    fetchConversations.mockRejectedValue(new Error("nope"));
    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
