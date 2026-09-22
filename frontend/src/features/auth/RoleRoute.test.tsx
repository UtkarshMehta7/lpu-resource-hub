import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { UserRead } from "./types";
import { RoleRoute } from "./RoleRoute";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));

vi.mock("./authContext", () => ({
  useAuth: useAuthMock,
}));

const ADMIN_USER: UserRead = {
  id: "1",
  email: "admin@example.com",
  full_name: "Admin User",
  role: "admin",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const STUDENT_USER: UserRead = { ...ADMIN_USER, role: "student", email: "student@example.com" };

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>Home page</p>} />
        <Route element={<RoleRoute allow={["admin"]} />}>
          <Route path="/admin/users" element={<p>Admin users page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("RoleRoute", () => {
  it("redirects away when there is no user", () => {
    useAuthMock.mockReturnValue({ user: null });

    renderAt("/admin/users");

    expect(screen.getByText("Home page")).toBeInTheDocument();
    expect(screen.queryByText("Admin users page")).not.toBeInTheDocument();
  });

  it("redirects away when the user's role is not allowed", () => {
    useAuthMock.mockReturnValue({ user: STUDENT_USER });

    renderAt("/admin/users");

    expect(screen.getByText("Home page")).toBeInTheDocument();
    expect(screen.queryByText("Admin users page")).not.toBeInTheDocument();
  });

  it("renders the route when the user's role is allowed", () => {
    useAuthMock.mockReturnValue({ user: ADMIN_USER });

    renderAt("/admin/users");

    expect(screen.getByText("Admin users page")).toBeInTheDocument();
  });
});
