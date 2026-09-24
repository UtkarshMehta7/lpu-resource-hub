import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as reactRouterDom from "react-router-dom";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandPalette } from "./CommandPalette";

const { useAuthMock, navigateMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("@/features/auth/authContext", () => ({ useAuth: useAuthMock }));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof reactRouterDom>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

function renderPalette(open = true) {
  const onClose = vi.fn();
  render(
    <MemoryRouter>
      <CommandPalette open={open} onClose={onClose} />
    </MemoryRouter>,
  );
  return { onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ user: { id: "u1", role: "admin" } });
});

describe("CommandPalette", () => {
  it("renders nothing while closed", () => {
    renderPalette(false);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("navigates on Enter, which is the whole point", async () => {
    const user = userEvent.setup();
    const { onClose } = renderPalette();

    await user.type(screen.getByLabelText("Go to page"), "verify");
    await user.keyboard("{Enter}");

    expect(navigateMock).toHaveBeenCalledWith("/coordinator/verification-queue");
    expect(onClose).toHaveBeenCalled();
  });

  it("moves the highlight with the arrow keys", async () => {
    const user = userEvent.setup();
    renderPalette();

    await user.type(screen.getByLabelText("Go to page"), "admin");
    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThan(1);
    const second = options[1]!.textContent ?? "";

    await user.keyboard("{ArrowDown}{Enter}");

    // It went to the second result, not the first -- which is what proves the
    // highlight moved rather than Enter simply taking the top hit.
    expect(navigateMock).toHaveBeenCalledTimes(1);
    const [target] = navigateMock.mock.calls[0] as [string];
    expect(second.toLowerCase()).toContain(
      target === "/admin" ? "administration" : target.split("/").pop()!.slice(0, 5),
    );
  });

  it("closes on Escape without going anywhere", async () => {
    const user = userEvent.setup();
    const { onClose } = renderPalette();

    await user.type(screen.getByLabelText("Go to page"), "acc");
    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("says so when nothing matches, rather than showing an empty box", async () => {
    const user = userEvent.setup();
    renderPalette();

    await user.type(screen.getByLabelText("Go to page"), "zzzzz");

    expect(screen.getByText(/nothing matches/i)).toBeInTheDocument();
  });

  it("offers a student nothing they cannot reach", async () => {
    useAuthMock.mockReturnValue({ user: { id: "u2", role: "student" } });
    const user = userEvent.setup();
    renderPalette();

    await user.type(screen.getByLabelText("Go to page"), "audit");

    expect(screen.getByText(/nothing matches/i)).toBeInTheDocument();
  });

  it("can be used with the mouse too", async () => {
    const user = userEvent.setup();
    renderPalette();

    await user.type(screen.getByLabelText("Go to page"), "audit");
    await user.click(screen.getByRole("option", { name: /Audit log/ }));

    expect(navigateMock).toHaveBeenCalledWith("/admin/audit-logs");
  });
});
