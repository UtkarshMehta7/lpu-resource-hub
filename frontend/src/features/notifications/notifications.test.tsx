import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AppNotification } from "./api";
import { describeNotification } from "./describe";
import { NotificationBell } from "./NotificationBell";
import { NotificationsPage } from "./NotificationsPage";

const { fetchMock, markOneMock, markAllMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  markOneMock: vi.fn(),
  markAllMock: vi.fn(),
}));

vi.mock("./api", () => ({
  fetchNotifications: fetchMock,
  markNotificationRead: markOneMock,
  markAllNotificationsRead: markAllMock,
}));

function notification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    notification_type: "application_decided",
    payload: {
      opportunity_id: "o1",
      opportunity_title: "Field assistant",
      status: "under_review",
      note: "Shortlisting next week",
    },
    read_at: null,
    created_at: "2026-09-23T09:00:00Z",
    ...overrides,
  };
}

function renderWith(component: React.ReactElement) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{component}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("describeNotification", () => {
  it("builds a line and a link from the stored payload alone", () => {
    expect(describeNotification(notification())).toEqual({
      text: "Your application to “Field assistant” is under review",
      to: "/me/applications",
      detail: "Shortlisting next week",
    });
  });

  it("renders a collaboration suggestion and links to the person", () => {
    // Same reason as the message case below: a notification type with no
    // case here is delivered and invisible, and every other test still
    // passes. The UID is in the detail because names collide.
    expect(
      describeNotification(
        notification({
          notification_type: "collaboration_suggestion",
          payload: {
            user_id: "u9",
            full_name: "Neha Gupta",
            registration_number: "12400112",
            score: 0.72,
            reasons: ["Shares 3 skills with you", "Both work on remote sensing"],
          },
        }),
      ),
    ).toEqual({
      text: "Neha Gupta works on similar things, and you have not published together",
      to: "/researchers/u9",
      detail: "12400112 · Shares 3 skills with you",
    });
  });

  it("reads an escalation as somebody pointing at YOUR work", () => {
    // Every other nudge is somebody chasing their own thing. If an escalation
    // used the same wording, the coordinator would read "is waiting on" and
    // misunderstand who is waiting for whom.
    expect(
      describeNotification(
        notification({
          notification_type: "nudge_received",
          payload: {
            kind: "project_at_risk",
            entity_id: "p1",
            from_name: "Vikram Chopra",
            from_registration_number: "12400501",
            subject: "“Soil moisture sensing”, which is slipping",
          },
        }),
      ),
    ).toEqual({
      text: "Vikram Chopra asked you to look at “Soil moisture sensing”, which is slipping",
      to: "/projects/p1",
      detail: "12400501",
    });
  });

  it("renders a message notification and links to the thread", () => {
    // The admin OTP once shipped invisible because this switch had no case
    // for it, and every test still passed. This is that test, for chat.
    expect(
      describeNotification(
        notification({
          notification_type: "message_received",
          payload: {
            conversation_id: "c1",
            sender_name: "Demo Faculty 07",
            preview: "Welcome aboard",
          },
        }),
      ),
    ).toEqual({
      text: "Demo Faculty 07 sent you a message",
      to: "/messages/c1",
      detail: "Welcome aboard",
    });
  });

  it("links a deadline reminder to the thing that's closing", () => {
    const line = describeNotification(
      notification({
        notification_type: "deadline_reminder",
        payload: { kind: "funding", item_id: "f1", title: "Demo seed grant", days_left: 1 },
      }),
    );
    expect(line.text).toBe("“Demo seed grant” closes in 1 day");
    expect(line.to).toBe("/funding/f1");
  });

  it("shows the first match reason for a relevant opportunity", () => {
    const line = describeNotification(
      notification({
        notification_type: "relevant_opportunity",
        payload: {
          opportunity_id: "o9",
          opportunity_title: "Sensor calibration",
          reasons: ["Matches 2 of 2 required skills: Sensors, Python"],
        },
      }),
    );
    expect(line.to).toBe("/opportunities/o9");
    expect(line.detail).toBe("Matches 2 of 2 required skills: Sensors, Python");
  });

  it("degrades gracefully for a type it doesn't know", () => {
    const line = describeNotification(
      notification({ notification_type: "something_new" as AppNotification["notification_type"] }),
    );
    expect(line).toEqual({ text: "You have a new notification", to: null });
  });
});

describe("NotificationBell", () => {
  beforeEach(() => fetchMock.mockReset());

  it("shows the unread count", async () => {
    fetchMock.mockResolvedValue({ unread_count: 3, items: [] });
    renderWith(<NotificationBell />);

    expect(await screen.findByRole("link", { name: /3 unread/i })).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows no badge when everything is read", async () => {
    fetchMock.mockResolvedValue({ unread_count: 0, items: [] });
    renderWith(<NotificationBell />);

    expect(await screen.findByRole("link", { name: "Notifications" })).toBeInTheDocument();
  });
});

describe("NotificationsPage", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    markOneMock.mockReset();
    markAllMock.mockReset();
  });

  it("lists notifications and marks one read", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue({ unread_count: 1, items: [notification()] });
    markOneMock.mockResolvedValue(notification({ read_at: "2026-09-23T10:00:00Z" }));
    renderWith(<NotificationsPage />);

    expect(
      await screen.findByText("Your application to “Field assistant” is under review"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /mark read/i }));
    await vi.waitFor(() => expect(markOneMock).toHaveBeenCalledWith("n1"));
  });

  it("offers mark-all only when something is unread", async () => {
    fetchMock.mockResolvedValue({
      unread_count: 0,
      items: [notification({ read_at: "2026-09-23T10:00:00Z" })],
    });
    renderWith(<NotificationsPage />);

    await screen.findByText("Your application to “Field assistant” is under review");
    expect(screen.queryByRole("button", { name: /mark all read/i })).toBeNull();
  });
});
