import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ProjectFormPage } from "./ProjectFormPage";

const { createProjectMock } = vi.hoisted(() => ({ createProjectMock: vi.fn() }));

vi.mock("./api", () => ({
  createProject: createProjectMock,
  updateProject: vi.fn(),
  fetchProject: vi.fn(),
}));

vi.mock("@/features/taxonomy/api", () => ({
  searchSkills: vi.fn().mockResolvedValue([]),
  searchResearchAreas: vi.fn().mockResolvedValue([]),
}));

function renderForm() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ProjectFormPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProjectFormPage", () => {
  it("requires title, summary and description", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /create draft/i }));

    expect(await screen.findByText(/title is required/i)).toBeInTheDocument();
    expect(screen.getByText(/summary is required/i)).toBeInTheDocument();
    expect(screen.getByText(/description is required/i)).toBeInTheDocument();
    expect(createProjectMock).not.toHaveBeenCalled();
  });

  it("rejects an end date before the start date", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText(/^title$/i), "Soil sensors");
    await user.type(screen.getByLabelText(/^summary$/i), "Cheap sensors");
    await user.type(screen.getByLabelText(/^description$/i), "Field tests");
    await user.type(screen.getByLabelText(/start date/i), "2026-12-01");
    await user.type(screen.getByLabelText(/end date/i), "2026-01-01");
    await user.click(screen.getByRole("button", { name: /create draft/i }));

    expect(await screen.findByText(/end date must be on or after/i)).toBeInTheDocument();
    expect(createProjectMock).not.toHaveBeenCalled();
  });
});
