import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SaveButton } from "./SaveButton";

const { fetchSavedMock, saveMock, unsaveMock } = vi.hoisted(() => ({
  fetchSavedMock: vi.fn(),
  saveMock: vi.fn(),
  unsaveMock: vi.fn(),
}));

vi.mock("./api", () => ({
  fetchSaved: fetchSavedMock,
  saveItem: saveMock,
  unsaveItem: unsaveMock,
}));

function renderButton() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SaveButton type="project" targetId="p1" />
    </QueryClientProvider>,
  );
}

describe("SaveButton", () => {
  beforeEach(() => {
    fetchSavedMock.mockReset();
    saveMock.mockReset();
    unsaveMock.mockReset();
  });

  it("saves an item that isn't saved yet", async () => {
    const user = userEvent.setup();
    fetchSavedMock.mockResolvedValue([]);
    saveMock.mockResolvedValue({});
    renderButton();

    const button = await screen.findByRole("button", { name: /save/i });
    expect(button).toHaveAttribute("aria-pressed", "false");
    await user.click(button);

    await vi.waitFor(() => expect(saveMock).toHaveBeenCalledWith({ project_id: "p1" }));
    expect(unsaveMock).not.toHaveBeenCalled();
  });

  it("removes an existing bookmark instead of saving twice", async () => {
    const user = userEvent.setup();
    fetchSavedMock.mockResolvedValue([
      { id: "s1", saved_type: "project", created_at: "", item: { id: "p1", title: "Soil" } },
    ]);
    renderButton();

    const button = await screen.findByRole("button", { name: /saved/i });
    expect(button).toHaveAttribute("aria-pressed", "true");
    await user.click(button);

    await vi.waitFor(() => expect(unsaveMock).toHaveBeenCalledWith("s1"));
    expect(saveMock).not.toHaveBeenCalled();
  });
});
