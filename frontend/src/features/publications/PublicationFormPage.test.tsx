import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { newAuthorRow, toAuthorInputs } from "./authors";
import { PublicationFormPage } from "./PublicationFormPage";

const { createPublicationMock } = vi.hoisted(() => ({ createPublicationMock: vi.fn() }));

vi.mock("./api", () => ({
  createPublication: createPublicationMock,
  updatePublication: vi.fn(),
  fetchPublication: vi.fn(),
}));

vi.mock("@/features/projects/api", () => ({
  fetchProjects: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
}));

vi.mock("@/features/directory/api", () => ({ fetchResearchers: vi.fn() }));

vi.mock("@/features/auth/authContext", () => ({
  useAuth: () => ({ user: { id: "u1", full_name: "Demo Faculty", role: "faculty" } }),
}));

function renderForm() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <PublicationFormPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("toAuthorInputs", () => {
  it("keeps order and maps each row to exactly one identity", () => {
    expect(
      toAuthorInputs([
        newAuthorRow("external", null, " Jane "),
        newAuthorRow("user", "u1", "Demo"),
      ]),
    ).toEqual([{ external_name: "Jane" }, { user_id: "u1" }]);
  });

  it("rejects empty lists and incomplete rows", () => {
    expect(toAuthorInputs([])).toMatch(/at least one author/i);
    expect(toAuthorInputs([newAuthorRow("user")])).toMatch(/pick a researcher/i);
    expect(toAuthorInputs([newAuthorRow("external")])).toMatch(/needs a name/i);
  });
});

describe("PublicationFormPage", () => {
  it("pre-fills the current user as first author and validates fields", async () => {
    const user = userEvent.setup();
    renderForm();

    expect(screen.getByText("Demo Faculty")).toBeInTheDocument();
    const year = screen.getByLabelText(/^year$/i);
    await user.clear(year);
    await user.type(year, "1500");
    await user.type(screen.getByLabelText(/^url/i), "ftp://example.com");
    await user.click(screen.getByRole("button", { name: /add publication/i }));

    expect(await screen.findByText(/title is required/i)).toBeInTheDocument();
    expect(screen.getByText(/between 1900 and 2100/i)).toBeInTheDocument();
    expect(screen.getByText(/must start with http/i)).toBeInTheDocument();
    expect(createPublicationMock).not.toHaveBeenCalled();
  });

  it("blocks submit when an author row is incomplete", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/^title$/i), "Paper");
    await user.click(screen.getByRole("button", { name: /\+ external author/i }));
    await user.click(screen.getByRole("button", { name: /add publication/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/needs a name/i);
    expect(createPublicationMock).not.toHaveBeenCalled();
  });
});
