import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as RouterModule from "react-router-dom";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { navigationFor, searchNavigation } from "@/components/layout/navigation";
import type { Role } from "@/features/auth/types";

import type * as ApiModule from "./api";
import { AnnouncementDetailPage } from "./AnnouncementDetailPage";
import { AnnouncementsPage } from "./AnnouncementsPage";
import type { Announcement } from "./api";
import { audienceLabel, posterLabel } from "./labels";

const {
  fetchAnnouncements,
  fetchAnnouncement,
  fetchUnreadCount,
  markAnnouncementRead,
  publishAnnouncement,
  withdrawAnnouncement,
  deleteAnnouncement,
  downloadAnnouncementAttachment,
  loadAnnouncementImage,
  useAuthMock,
} = vi.hoisted(() => ({
  fetchAnnouncements: vi.fn(),
  fetchAnnouncement: vi.fn(),
  fetchUnreadCount: vi.fn(),
  markAnnouncementRead: vi.fn(),
  publishAnnouncement: vi.fn(),
  withdrawAnnouncement: vi.fn(),
  deleteAnnouncement: vi.fn(),
  downloadAnnouncementAttachment: vi.fn(),
  loadAnnouncementImage: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    fetchAnnouncements,
    fetchAnnouncement,
    fetchUnreadCount,
    markAnnouncementRead,
    publishAnnouncement,
    withdrawAnnouncement,
    deleteAnnouncement,
    downloadAnnouncementAttachment,
    loadAnnouncementImage,
  };
});
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof RouterModule>();
  return { ...actual, useParams: () => ({ announcementId: "a1" }) };
});

function notice(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "a1",
    subject: "Invention disclosure window closes on Friday",
    body: "Send your disclosures to the IP cell before 5 pm on Friday.",
    audience: "institution",
    department_id: null,
    department_name: null,
    posted_by: "u-admin",
    posted_by_name: "Harpreet Kaur",
    posted_by_role: "admin",
    status: "published",
    published_at: "2026-10-09T09:00:00Z",
    links: [],
    attachments: [],
    unread: false,
    created_at: "2026-10-09T08:00:00Z",
    updated_at: "2026-10-09T09:00:00Z",
    ...overrides,
  };
}

function pageOf(items: Announcement[]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

function signedInAs(role: Role, id = "u-me") {
  useAuthMock.mockReturnValue({ user: { id, role, full_name: "Somebody" } });
}

function testClient() {
  // No retries: a test for the not-found state would otherwise wait out
  // three attempts before rendering it.
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderBoard(mine = false) {
  render(
    <QueryClientProvider client={testClient()}>
      <MemoryRouter>
        <AnnouncementsPage mine={mine} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderDetail() {
  render(
    <QueryClientProvider client={testClient()}>
      <MemoryRouter>
        <AnnouncementDetailPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchAnnouncements.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
  fetchUnreadCount.mockResolvedValue(0);
  markAnnouncementRead.mockResolvedValue(undefined);
});

describe("the notice board", () => {
  it("shows a notice with who said it and how far it reached", async () => {
    signedInAs("student");
    fetchAnnouncements.mockResolvedValue({
      items: [notice()],
      page: 1,
      page_size: 20,
      total: 1,
    });

    renderBoard();

    expect(
      await screen.findByText("Invention disclosure window closes on Friday"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Harpreet Kaur/)).toBeInTheDocument();
    expect(screen.getByText("Whole university")).toBeInTheDocument();
  });

  it("names the department a departmental notice was addressed to", async () => {
    // "Department" alone leaves a reader on three committees guessing which.
    signedInAs("student");
    fetchAnnouncements.mockResolvedValue({
      items: [
        notice({
          audience: "department",
          department_id: "d1",
          department_name: "Computer Science and Engineering",
          posted_by_role: "research_coordinator",
        }),
      ],
      page: 1,
      page_size: 20,
      total: 1,
    });

    renderBoard();

    expect(await screen.findByText("Computer Science and Engineering")).toBeInTheDocument();
  });

  it("marks an unread notice with a word and not only a colour", async () => {
    signedInAs("student");
    fetchAnnouncements.mockResolvedValue({
      items: [notice({ unread: true })],
      page: 1,
      page_size: 20,
      total: 1,
    });

    renderBoard();

    expect(await screen.findByText("New")).toBeInTheDocument();
  });

  it("offers the post action to the posting roles", async () => {
    for (const role of ["research_coordinator", "dean_of_research", "admin"] as Role[]) {
      signedInAs(role);
      renderBoard();
      expect(await screen.findByRole("link", { name: "Post a notice" })).toBeInTheDocument();
      cleanup();
    }
  });

  it("withholds it from the roles that only read", async () => {
    for (const role of ["student", "faculty", "facility_custodian"] as Role[]) {
      signedInAs(role);
      renderBoard();
      await waitFor(() => expect(fetchAnnouncements).toHaveBeenCalled());
      expect(screen.queryByRole("link", { name: "Post a notice" })).not.toBeInTheDocument();
      cleanup();
    }
  });

  it("says what to do next when there is nothing", async () => {
    signedInAs("student");

    renderBoard();

    expect(await screen.findByText("No announcements yet")).toBeInTheDocument();
  });

  it("says something different when the filter is what emptied it", async () => {
    signedInAs("student");

    render(
      <QueryClientProvider client={testClient()}>
        <MemoryRouter initialEntries={["/announcements?unread_only=true"]}>
          <AnnouncementsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Nothing unread")).toBeInTheDocument();
  });
});

describe("reading a notice", () => {
  it("marks it read on opening, because opening it is reading it", async () => {
    signedInAs("student");
    fetchAnnouncement.mockResolvedValue(notice({ unread: true }));

    renderDetail();

    await waitFor(() => expect(markAnnouncementRead).toHaveBeenCalledWith("a1"));
  });

  it("does not post a read marker for one already read", async () => {
    signedInAs("student");
    fetchAnnouncement.mockResolvedValue(notice({ unread: false }));

    renderDetail();

    expect(await screen.findByText(/Send your disclosures/)).toBeInTheDocument();
    expect(markAnnouncementRead).not.toHaveBeenCalled();
  });

  it("opens a link in a new tab without handing over the opener", async () => {
    signedInAs("student");
    fetchAnnouncement.mockResolvedValue(
      notice({ links: [{ id: "l1", label: "The form", url: "https://example.org/form" }] }),
    );

    renderDetail();

    const link = await screen.findByRole("link", { name: "The form" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("downloads an attachment through the API rather than a plain link", async () => {
    // An <a href> carries no Authorization header, so a departmental
    // notice's file would be reachable by whoever held the URL.
    signedInAs("student");
    const attachment = {
      id: "f1",
      filename: "circular.pdf",
      content_type: "application/pdf",
      byte_size: 2048,
    };
    fetchAnnouncement.mockResolvedValue(notice({ attachments: [attachment] }));

    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: /circular\.pdf/ }));

    expect(downloadAnnouncementAttachment).toHaveBeenCalledWith("a1", attachment);
  });

  it("renders an image attachment from fetched bytes", async () => {
    signedInAs("student");
    loadAnnouncementImage.mockResolvedValue("blob:poster");
    fetchAnnouncement.mockResolvedValue(
      notice({
        attachments: [
          {
            id: "f2",
            filename: "poster.png",
            content_type: "image/png",
            byte_size: 4096,
          },
        ],
      }),
    );

    renderDetail();

    const image = await screen.findByRole("img", { name: "poster.png" });
    expect(image).toHaveAttribute("src", "blob:poster");
  });

  it("says plainly when a notice is not addressed to you", async () => {
    signedInAs("student");
    fetchAnnouncement.mockRejectedValue(new Error("404"));

    renderDetail();

    expect(await screen.findByText("Announcement not found")).toBeInTheDocument();
  });
});

describe("the author's own controls", () => {
  it("offers publish on a draft, and warns that publishing is final", async () => {
    signedInAs("admin", "u-admin");
    fetchAnnouncement.mockResolvedValue(
      notice({ status: "draft", published_at: null, posted_by: "u-admin" }),
    );
    publishAnnouncement.mockResolvedValue(notice());

    renderDetail();

    expect(await screen.findByRole("button", { name: "Publish" })).toBeInTheDocument();
    expect(screen.getByText(/cannot be changed/)).toBeInTheDocument();
  });

  it("does not offer publish on somebody else's draft", async () => {
    signedInAs("admin", "u-admin");
    fetchAnnouncement.mockResolvedValue(
      notice({ status: "draft", published_at: null, posted_by: "u-someone-else" }),
    );

    renderDetail();

    expect(await screen.findByText(/Send your disclosures/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });

  it("lets an admin withdraw somebody else's published notice", async () => {
    signedInAs("admin", "u-admin");
    fetchAnnouncement.mockResolvedValue(notice({ posted_by: "u-someone-else" }));
    withdrawAnnouncement.mockResolvedValue(notice({ status: "withdrawn" }));

    renderDetail();

    await userEvent.click(await screen.findByRole("button", { name: "Withdraw" }));
    // A different word on the confirm, so this click cannot land on the
    // button that opened the dialog.
    await userEvent.click(screen.getByRole("button", { name: "Withdraw it", hidden: true }));

    await waitFor(() => expect(withdrawAnnouncement).toHaveBeenCalled());
  });

  it("does not let a reader withdraw anything", async () => {
    signedInAs("faculty");
    fetchAnnouncement.mockResolvedValue(notice());

    renderDetail();

    expect(await screen.findByText(/Send your disclosures/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Withdraw" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("offers no edit once it is published, even to its author", async () => {
    signedInAs("admin", "u-admin");
    fetchAnnouncement.mockResolvedValue(notice({ posted_by: "u-admin" }));

    renderDetail();

    expect(await screen.findByText(/Send your disclosures/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit" })).not.toBeInTheDocument();
  });
});

describe("the labels", () => {
  it("names the poster's role as it was when they posted", () => {
    expect(posterLabel(notice({ posted_by_role: "dean_of_research" }))).toContain(
      "Dean of Research",
    );
  });

  it("falls back to the word when a department name is missing", () => {
    // A deleted department cascades the notice away, so this is defence
    // rather than an expected state -- but it must not render "null".
    expect(audienceLabel(notice({ audience: "department", department_name: null }))).toBe(
      "Department",
    );
  });
});

describe("reachability", () => {
  it("is in the one navigation list, for every role", () => {
    for (const role of [
      "student",
      "faculty",
      "research_coordinator",
      "facility_custodian",
      "dean_of_research",
      "admin",
    ] as Role[]) {
      const paths = navigationFor(role).map((item) => item.to);
      expect(paths).toContain("/announcements");
    }
  });

  it("offers posting in the navigation only to the roles that may", () => {
    for (const role of ["research_coordinator", "dean_of_research", "admin"] as Role[]) {
      expect(navigationFor(role).map((item) => item.to)).toContain("/announcements/new");
    }
    for (const role of ["student", "faculty", "facility_custodian"] as Role[]) {
      expect(navigationFor(role).map((item) => item.to)).not.toContain("/announcements/new");
    }
  });

  it("is findable in the command palette by the words people use", () => {
    const items = navigationFor("student");
    for (const query of ["announce", "notice", "circular", "bulletin"]) {
      expect(searchNavigation(items, query).map((item) => item.to)).toContain("/announcements");
    }
  });
});

describe("a notice raised from an opening", () => {
  it("is marked on the board, so hiring does not read as circulars", async () => {
    signedInAs("student");
    fetchAnnouncements.mockResolvedValue(
      pageOf([
        notice({
          subject: "Opening: Research assistant for soil sensors",
          source_opportunity_id: "op-1",
        }),
      ]),
    );

    renderBoard();

    expect(await screen.findByText(/Opening: Research assistant/)).toBeInTheDocument();
    expect(screen.getByText("Opening")).toBeInTheDocument();
  });

  it("leaves a hand-written notice unmarked", async () => {
    signedInAs("student");
    fetchAnnouncements.mockResolvedValue(pageOf([notice()]));

    renderBoard();

    expect(await screen.findByText(/disclosure window/i)).toBeInTheDocument();
    expect(screen.queryByText("Opening")).not.toBeInTheDocument();
  });

  it("carries the reader to the position rather than its title alone", async () => {
    signedInAs("student");
    fetchAnnouncement.mockResolvedValue(notice({ source_opportunity_id: "op-1" }));

    renderDetail();

    expect(await screen.findByRole("link", { name: "Open the position" })).toHaveAttribute(
      "href",
      "/opportunities/op-1",
    );
  });

  it("renders when the API is older than the page and omits the field", async () => {
    // Netlify deploys in seconds, Render in minutes.
    signedInAs("student");
    const { source_opportunity_id, ...withoutField } = notice();
    void source_opportunity_id;
    fetchAnnouncement.mockResolvedValue(withoutField);

    renderDetail();

    expect(await screen.findByText(/disclosures to the IP cell/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Open the position" })).not.toBeInTheDocument();
  });
});
