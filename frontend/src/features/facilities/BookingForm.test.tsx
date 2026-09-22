import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingForm } from "./BookingForm";
import type { Equipment } from "./api";

const { createBookingMock } = vi.hoisted(() => ({ createBookingMock: vi.fn() }));

vi.mock("./api", () => ({ createBooking: createBookingMock }));

const EQUIPMENT: Equipment = {
  id: "e1",
  facility_id: "f1",
  facility_name: "Soil Lab",
  department_id: null,
  name: "Soil moisture probe",
  description: null,
  category: "sensors",
  maintenance_status: "available",
  students_allowed: true,
  requires_approval: true,
  max_hours: 4,
  min_lead_hours: 2,
  created_at: "",
};

function renderForm(equipment: Equipment = EQUIPMENT) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BookingForm
        equipment={equipment}
        date="2026-09-21"
        hour={9}
        onDateChange={() => {}}
        onHourChange={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe("BookingForm", () => {
  beforeEach(() => createBookingMock.mockReset());

  it("asks what the equipment is needed for", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /request this slot/i }));

    expect(await screen.findByText(/say briefly what you need it for/i)).toBeInTheDocument();
    expect(createBookingMock).not.toHaveBeenCalled();
  });

  it("refuses a period longer than the equipment allows", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/what do you need it for/i), "Calibrating the probes");
    const hours = screen.getByLabelText(/hours \(max 4\)/i);
    await user.clear(hours);
    await user.type(hours, "6");
    await user.click(screen.getByRole("button", { name: /request this slot/i }));

    expect(await screen.findByText(/at most 4 hours/i)).toBeInTheDocument();
    expect(createBookingMock).not.toHaveBeenCalled();
  });

  it("sends the picked slot and reports what happened", async () => {
    const user = userEvent.setup();
    createBookingMock.mockResolvedValue({ status: "pending" });
    renderForm();

    await user.type(screen.getByLabelText(/what do you need it for/i), "Calibrating the probes");
    await user.click(screen.getByRole("button", { name: /request this slot/i }));

    await vi.waitFor(() => expect(createBookingMock).toHaveBeenCalledTimes(1));
    const payload = createBookingMock.mock.calls[0]?.[0] as {
      equipment_id: string;
      starts_at: string;
      ends_at: string;
      purpose: string;
    };
    expect(payload.equipment_id).toBe("e1");
    expect(new Date(payload.starts_at).getHours()).toBe(9);
    expect(new Date(payload.ends_at).getHours()).toBe(10);
    expect(payload.purpose).toBe("Calibrating the probes");
    expect(await screen.findByText(/coordinator will review it/i)).toBeInTheDocument();
  });

  it("says so instead of offering a form when the equipment is down", () => {
    renderForm({ ...EQUIPMENT, maintenance_status: "maintenance" });

    expect(screen.getByText(/under maintenance/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /request this slot/i })).toBeNull();
  });
});
