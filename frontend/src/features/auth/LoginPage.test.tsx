import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { LoginPage } from "./LoginPage";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));

vi.mock("./authContext", () => ({
  useAuth: useAuthMock,
}));

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage validation", () => {
  it("shows validation errors and never calls login when the form is empty", async () => {
    const login = vi.fn();
    useAuthMock.mockReturnValue({ login });
    const user = userEvent.setup();

    renderLoginPage();
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByText(/registration number is required/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("rejects a registration number that is too long", async () => {
    const login = vi.fn();
    useAuthMock.mockReturnValue({ login });
    const user = userEvent.setup();

    renderLoginPage();
    await user.type(screen.getByLabelText(/registration number/i), "X".repeat(51));
    await user.type(screen.getByLabelText(/password/i), "whatever");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByText(/too long for a registration number/i)).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("calls login with valid credentials", async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    useAuthMock.mockReturnValue({ login });
    const user = userEvent.setup();

    renderLoginPage();
    await user.type(screen.getByLabelText(/registration number/i), "12345678");
    await user.type(screen.getByLabelText(/password/i), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(login).toHaveBeenCalledWith({
      registration_number: "12345678",
      password: "correcthorsebattery",
    });
  });
});
