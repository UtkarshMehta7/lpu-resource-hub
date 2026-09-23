import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModuleType from "./api";
import { FacilityDetailPage } from "./FacilityDetailPage";

type ApiModule = typeof ApiModuleType;

const { fetchFacility, fetchEquipmentList, updateFacility, deleteFacility, useAuthMock } =
  vi.hoisted(() => ({
    fetchFacility: vi.fn(),
    fetchEquipmentList: vi.fn(),
    updateFacility: vi.fn(),
    deleteFacility: vi.fn(),
    useAuthMock: vi.fn(),
  }));

// Keep the real MAINTENANCE_LABEL and friends; replace only the requests.
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<ApiModule>()),
  fetchFacility,
  fetchEquipmentList,
  updateFacility,
  deleteFacility,
}));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const FACILITY = {
  id: "f1",
  name: "Soil Lab",
  description: "Soil analysis.",
  department_id: "d1",
  location: "Block 32",
  contact: "ext 4102",
  equipment_count: 2,
  created_at: "2026-01-01T00:00:00Z",
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
