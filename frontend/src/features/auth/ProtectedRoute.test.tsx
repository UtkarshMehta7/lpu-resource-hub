import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ProtectedRoute } from "./ProtectedRoute";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));

vi.mock("./authContext", () => ({
  useAuth: useAuthMock,
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>Login page</p>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/account" element={<p>Protected account content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("shows a loading state while the session is still being restored", () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: true });

    renderAt("/account");

    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
  });

  it("redirects to /login when not authenticated", () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });

    renderAt("/account");

    expect(screen.getByText("Login page")).toBeInTheDocument();
    expect(screen.queryByText("Protected account content")).not.toBeInTheDocument();
  });

  it("renders the protected route when authenticated", () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });

    renderAt("/account");

    expect(screen.getByText("Protected account content")).toBeInTheDocument();
  });
});
