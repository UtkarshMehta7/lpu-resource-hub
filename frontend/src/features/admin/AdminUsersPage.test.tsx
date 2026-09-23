import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminUsersPage } from "./AdminUsersPage";
import type { AdminUserRead } from "./types";

const { fetchUsers, updateUser, resetTemporaryPassword, fetchDepartments, useAuthMock } =
  vi.hoisted(() => ({
    fetchUsers: vi.fn(),
    updateUser: vi.fn(),
    resetTemporaryPassword: vi.fn(),
    fetchDepartments: vi.fn(),
    useAuthMock: vi.fn(),
  }));

vi.mock("./api", () => ({
  fetchUsers,
  updateUser,
  resetTemporaryPassword,
  changeUserRole: vi.fn(),
  setUserActive: vi.fn(),
}));

vi.mock("@/features/directory/api-org", () => ({ fetchDepartments }));
vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));

const STRANDED: AdminUserRead = {
  id: "user-1",
  registration_number: "DEMOFACULTY01",
  email: "someone@example.com",
  full_name: "Demo Faculty 01",
  role: "faculty",
  is_active: true,
  must_change_password: false,
  department_id: null,
  coordinator_scope_type: null,
  coordinator_scope_id: null,
  created_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminUsersPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "admin-1", role: "admin" } });
  fetchUsers.mockResolvedValue({ items: [STRANDED], page: 1, page_size: 100, total: 1 });
  fetchDepartments.mockResolvedValue([{ id: "dept-1", name: "Agriculture", school_id: "s-1" }]);
  updateUser.mockResolvedValue({ ...STRANDED, department_id: "dept-1" });
});

describe("AdminUsersPage", () => {
  it("places a user who has no department", async () => {
    const user = userEvent.setup();
    renderPage();

    const select = await screen.findByLabelText(/department for demo faculty 01/i);
    expect(select).toHaveValue("");

    await user.selectOptions(select, "dept-1");

    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith("user-1", { department_id: "dept-1" }),
    );
  });

  it("clears a department back to none", async () => {
    const user = userEvent.setup();
    fetchUsers.mockResolvedValue({
      items: [{ ...STRANDED, department_id: "dept-1" }],
      page: 1,
      page_size: 100,
      total: 1,
    });
    renderPage();

    await user.selectOptions(await screen.findByLabelText(/department for/i), "");

    await waitFor(() => expect(updateUser).toHaveBeenCalledWith("user-1", { department_id: null }));
  });

  it("renames a user", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /rename demo faculty 01/i }));
    const input = screen.getByLabelText(/name for demo faculty 01/i);
    await user.clear(input);
    await user.type(input, "Priya Sharma");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith("user-1", { full_name: "Priya Sharma" }),
    );
  });

  it("does not call the API when a rename changes nothing", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /rename/i }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateUser).not.toHaveBeenCalled();
  });

  it("shows a new temporary password once, after confirming", async () => {
    const user = userEvent.setup();
    resetTemporaryPassword.mockResolvedValue({
      user: { ...STRANDED, must_change_password: true },
      temporary_password: "Xy7NewTempPass",
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: /new password/i }));
    // Nothing happens until the confirmation is accepted.
    expect(resetTemporaryPassword).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    expect(await screen.findByText("Xy7NewTempPass")).toBeInTheDocument();
    expect(resetTemporaryPassword).toHaveBeenCalledWith("user-1");
  });

  it("surfaces the reason the API refused", async () => {
    const user = userEvent.setup();
    updateUser.mockRejectedValue(new Error("nope"));
    renderPage();

    await user.selectOptions(await screen.findByLabelText(/department for/i), "dept-1");

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
