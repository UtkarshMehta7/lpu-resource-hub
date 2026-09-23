import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminHandoverPage } from "./AdminHandoverPage";
import type { AdminUserRead } from "./types";

const { fetchUsers, requestAdminPromotion, confirmAdminPromotion, stepDownAsAdmin, useAuthMock } =
  vi.hoisted(() => ({
    fetchUsers: vi.fn(),
    requestAdminPromotion: vi.fn(),
    confirmAdminPromotion: vi.fn(),
    stepDownAsAdmin: vi.fn(),
    useAuthMock: vi.fn(),
  }));

vi.mock("./api", () => ({
  fetchUsers,
  requestAdminPromotion,
  confirmAdminPromotion,
  stepDownAsAdmin,
}));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

function person(overrides: Partial<AdminUserRead> = {}): AdminUserRead {
  return {
    id: "u1",
    registration_number: "DEMOFACULTY01",
    email: "someone@example.com",
    full_name: "Demo Faculty 01",
    role: "faculty",
    is_active: true,
    must_change_password: false,
    department_id: null,
    created_by: null,
    coordinator_scope_type: null,
    coordinator_scope_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminHandoverPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "admin-1", role: "admin", full_name: "Demo Admin" } });
  // Two calls: the candidate list, and the admin head-count.
  fetchUsers.mockImplementation((params: { role?: string }) =>
    Promise.resolve(
      params.role === "admin"
        ? { items: [], page: 1, page_size: 1, total: 1 }
        : { items: [person()], page: 1, page_size: 100, total: 1 },
    ),
  );
  requestAdminPromotion.mockResolvedValue({
    id: "c1",
    target_user_id: "u1",
    expires_at: "2026-09-23T12:20:00Z",
  });
  confirmAdminPromotion.mockResolvedValue(person({ role: "admin" }));
});

describe("AdminHandoverPage", () => {
  it("sends the code to the person being promoted, and never shows it", async () => {
    const user = userEvent.setup();
    renderPage();

    // The select renders before its options arrive, so wait for the person.
    await screen.findByRole("option", { name: /Demo Faculty 01/ });
    await user.selectOptions(screen.getByLabelText(/person to promote/i), "u1");
    await user.click(screen.getByRole("button", { name: "Send code" }));

    await waitFor(() => expect(requestAdminPromotion).toHaveBeenCalledWith("u1"));
    expect(await screen.findByText(/expires at/i)).toBeInTheDocument();
    // The requester's half of the ceremony never learns the digits.
    expect(screen.queryByText(/\b\d{6}\b/)).not.toBeInTheDocument();
  });

  it("cannot send a code before choosing someone", async () => {
    renderPage();

    expect(await screen.findByRole("button", { name: "Send code" })).toBeDisabled();
  });

  it("completes the promotion with the code read back", async () => {
    const user = userEvent.setup();
    renderPage();

    // The select renders before its options arrive, so wait for the person.
    await screen.findByRole("option", { name: /Demo Faculty 01/ });
    await user.selectOptions(screen.getByLabelText(/person to promote/i), "u1");
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(screen.getByLabelText(/confirmation code/i), "123456");
    await user.click(screen.getByRole("button", { name: "Promote" }));

    await waitFor(() => expect(confirmAdminPromotion).toHaveBeenCalledWith("u1", "123456"));
    expect(await screen.findByText(/is now an administrator/i)).toBeInTheDocument();
  });

  it("surfaces a refused code instead of pretending it worked", async () => {
    const user = userEvent.setup();
    confirmAdminPromotion.mockRejectedValue(new Error("That code is not right."));
    renderPage();

    // The select renders before its options arrive, so wait for the person.
    await screen.findByRole("option", { name: /Demo Faculty 01/ });
    await user.selectOptions(screen.getByLabelText(/person to promote/i), "u1");
    await user.click(screen.getByRole("button", { name: "Send code" }));
    await user.type(screen.getByLabelText(/confirmation code/i), "000000");
    await user.click(screen.getByRole("button", { name: "Promote" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/is now an administrator/i)).not.toBeInTheDocument();
  });

  it("refuses to offer stepping down while you are the only admin", async () => {
    renderPage();

    expect(await screen.findByText(/only administrator/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Step down" })).not.toBeInTheDocument();
  });

  it("offers stepping down once someone else holds the role", async () => {
    fetchUsers.mockImplementation((params: { role?: string }) =>
      Promise.resolve(
        params.role === "admin"
          ? { items: [], page: 1, page_size: 1, total: 2 }
          : { items: [person()], page: 1, page_size: 100, total: 1 },
      ),
    );
    renderPage();

    expect(await screen.findByRole("button", { name: "Step down" })).toBeInTheDocument();
  });

  it("asks before giving up the role", async () => {
    const user = userEvent.setup();
    fetchUsers.mockImplementation((params: { role?: string }) =>
      Promise.resolve(
        params.role === "admin"
          ? { items: [], page: 1, page_size: 1, total: 2 }
          : { items: [person()], page: 1, page_size: 100, total: 1 },
      ),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Step down" }));

    expect(await screen.findByText(/Give up administrator\?/i)).toBeInTheDocument();
    expect(stepDownAsAdmin).not.toHaveBeenCalled();
  });
});
