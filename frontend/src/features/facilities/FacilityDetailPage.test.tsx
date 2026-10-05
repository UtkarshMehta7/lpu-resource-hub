import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModuleType from "./api";
import { FacilityDetailPage } from "./FacilityDetailPage";

type ApiModule = typeof ApiModuleType;

const {
  fetchFacility,
  fetchEquipmentList,
  updateFacility,
  deleteFacility,
  fetchCustodianCandidates,
  assignFacilityCustodian,
  useAuthMock,
} = vi.hoisted(() => ({
  fetchFacility: vi.fn(),
  fetchEquipmentList: vi.fn(),
  updateFacility: vi.fn(),
  deleteFacility: vi.fn(),
  fetchCustodianCandidates: vi.fn(),
  assignFacilityCustodian: vi.fn(),
  useAuthMock: vi.fn(),
}));

// Keep the real MAINTENANCE_LABEL and friends; replace only the requests.
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<ApiModule>()),
  fetchFacility,
  fetchEquipmentList,
  updateFacility,
  deleteFacility,
  fetchCustodianCandidates,
  assignFacilityCustodian,
}));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const FACILITY = {
  id: "f1",
  name: "Soil Lab",
  description: "Soil analysis.",
  department_id: "d1",
  location: "Block 32",
  contact: "ext 4102",
  custodian_id: null,
  custodian_name: null,
  custodian_registration_number: null,
  equipment_count: 2,
  created_at: "2026-01-01T00:00:00Z",
};

const HELD = {
  ...FACILITY,
  custodian_id: "c1",
  custodian_name: "Rohit Sharma",
  custodian_registration_number: "12500401",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/facilities/f1"]}>
        <Routes>
          <Route path="/facilities/:facilityId" element={<FacilityDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "a1", role: "admin" } });
  fetchFacility.mockResolvedValue(FACILITY);
  fetchEquipmentList.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
  fetchCustodianCandidates.mockResolvedValue([
    { id: "c1", full_name: "Rohit Sharma", registration_number: "12500401" },
  ]);
  assignFacilityCustodian.mockResolvedValue(HELD);
  updateFacility.mockResolvedValue({ ...FACILITY, name: "Soil Science Lab" });
  deleteFacility.mockResolvedValue(undefined);
});

describe("FacilityDetailPage", () => {
  it("renames a facility in place", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Rename Soil Lab/i }));
    const input = screen.getByLabelText(/Facility name/i);
    await user.clear(input);
    await user.type(input, "Soil Science Lab");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(updateFacility).toHaveBeenCalledWith("f1", { name: "Soil Science Lab" }),
    );
  });

  it("does not call the API when the name is unchanged", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Rename/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateFacility).not.toHaveBeenCalled();
  });

  it("asks before deleting, and says what is attached", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Delete facility" }));

    expect(await screen.findByText(/Delete this facility\?/i)).toBeInTheDocument();
    expect(screen.getByText(/2 items of equipment/i)).toBeInTheDocument();
    expect(deleteFacility).not.toHaveBeenCalled();
  });

  it("deletes once confirmed", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Delete facility" }));
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(deleteFacility).toHaveBeenCalledWith("f1"));
  });

  it("surfaces a refusal from the API", async () => {
    const user = userEvent.setup();
    updateFacility.mockRejectedValue(new Error("Outside your department."));
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Rename/i }));
    const input = screen.getByLabelText(/Facility name/i);
    await user.clear(input);
    await user.type(input, "Someone Else's Lab");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("offers none of it to someone who cannot manage facilities", async () => {
    useAuthMock.mockReturnValue({ user: { id: "s1", role: "student" } });
    renderPage();

    expect(await screen.findByRole("heading", { name: "Soil Lab" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Rename/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete facility" })).not.toBeInTheDocument();
  });
});

describe("the custodian panel", () => {
  it("names who looks after the facility, with their UID", async () => {
    fetchFacility.mockResolvedValue(HELD);
    renderPage();

    expect(await screen.findByText("Rohit Sharma")).toBeInTheDocument();
    expect(screen.getByText("12500401")).toBeInTheDocument();
  });

  it("says plainly when nobody does, and who covers until then", async () => {
    renderPage();

    expect(await screen.findByText(/Nobody looks after this facility yet/)).toBeInTheDocument();
  });

  it("lets a coordinator assign one from the server's own shortlist", async () => {
    const user = userEvent.setup();
    useAuthMock.mockReturnValue({ user: { id: "co1", role: "research_coordinator" } });
    renderPage();

    await screen.findByRole("option", { name: /Rohit Sharma/ });
    await user.selectOptions(screen.getByLabelText("Assign a custodian", { exact: true }), "c1");

    await waitFor(() => expect(assignFacilityCustodian).toHaveBeenCalledWith("f1", "c1"));
  });

  it("does not let a custodian hand their own facility away, or abolish it", async () => {
    fetchFacility.mockResolvedValue(HELD);
    useAuthMock.mockReturnValue({ user: { id: "c1", role: "facility_custodian" } });
    renderPage();

    // They hold this room, so they get the day-to-day controls...
    expect(await screen.findByRole("link", { name: "Add equipment" })).toBeInTheDocument();
    // ...but never the power to decide who holds it...
    expect(screen.queryByLabelText("Assign a custodian", { exact: true })).not.toBeInTheDocument();
    // ...nor to delete it. This asserted the opposite, which was true while
    // deletion was gated object-level like editing — and that let the person
    // who looks after a room destroy it, taking its equipment and every
    // booking held on it by cascade. Creating a facility is a department
    // decision; deleting one is the same decision in reverse.
    expect(screen.queryByRole("button", { name: "Delete facility" })).not.toBeInTheDocument();
  });

  it("gives a custodian nothing on a facility that is not theirs", async () => {
    fetchFacility.mockResolvedValue(HELD);
    useAuthMock.mockReturnValue({ user: { id: "someone-else", role: "facility_custodian" } });
    renderPage();

    await screen.findByText("Rohit Sharma");
    expect(screen.queryByRole("button", { name: "Delete facility" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Assign a custodian", { exact: true })).not.toBeInTheDocument();
  });
});
