import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Role } from "@/features/auth/types";

import type { Booking } from "./api";
import { BookingQueuePage } from "./BookingQueuePage";

const { fetchBookingQueue, decideBooking, useAuthMock } = vi.hoisted(() => ({
  fetchBookingQueue: vi.fn(),
  decideBooking: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock("./api", () => ({ fetchBookingQueue, decideBooking }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const WAITING: Booking = {
  id: "b1",
  equipment_id: "e1",
  equipment_name: "Centrifuge",
  facility_name: "Soil Lab",
  user_id: "u9",
  user_name: "Rohit Sharma",
  starts_at: "2026-10-10T09:00:00Z",
  ends_at: "2026-10-10T11:00:00Z",
  purpose: "Sample preparation.",
  status: "pending",
  decided_by: null,
  decided_at: null,
  decision_note: null,
  created_at: "2026-10-01T09:00:00Z",
};

function renderPage(role: Role) {
  useAuthMock.mockReturnValue({ user: { id: "me", role, full_name: "Signed in" } });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BookingQueuePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchBookingQueue.mockResolvedValue([WAITING]);
  decideBooking.mockResolvedValue({ ...WAITING, status: "approved" });
});

describe("BookingQueuePage", () => {
  it("tells a custodian the queue is their own facilities, not a department", async () => {
    renderPage("facility_custodian");

    expect(
      await screen.findByText(/Requests for equipment in the facilities assigned to you/),
    ).toBeInTheDocument();
  });

  it("still says department for a coordinator", async () => {
    renderPage("research_coordinator");

    expect(
      await screen.findByText(/Requests for equipment in your department/),
    ).toBeInTheDocument();
  });

  it("says the whole university for an administrator", async () => {
    renderPage("admin");

    expect(
      await screen.findByText(/Requests for equipment anywhere in the university/),
    ).toBeInTheDocument();
  });

  it("lets whoever is responsible approve what is waiting", async () => {
    const user = userEvent.setup();
    renderPage("facility_custodian");

    await screen.findByRole("link", { name: "Centrifuge" });
    await user.type(screen.getByLabelText(/Note to the requester/), "Booked.");
    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => expect(decideBooking).toHaveBeenCalledWith("b1", "approve", "Booked."));
  });
});
