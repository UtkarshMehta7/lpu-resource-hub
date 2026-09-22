import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TagPicker, type TagOption } from "./TagPicker";

const OPTIONS: TagOption[] = [
  { id: "1", name: "Machine Learning" },
  { id: "2", name: "Computer Vision" },
];

function renderPicker(overrides: Partial<React.ComponentProps<typeof TagPicker>> = {}) {
  const props = {
    label: "Skills",
    search: vi.fn().mockResolvedValue(OPTIONS),
    selected: [],
    onAdd: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
  render(<TagPicker {...props} />);
  return props;
}

describe("TagPicker", () => {
  it("shows search results and adds the chosen option", async () => {
    const user = userEvent.setup();
    const props = renderPicker();

    await user.type(screen.getByLabelText("Skills"), "mach");

    const result = await screen.findByRole("button", { name: "Machine Learning" });
    await user.click(result);

    expect(props.onAdd).toHaveBeenCalledWith({ id: "1", name: "Machine Learning" });
  });

  it("does not offer options that are already selected", async () => {
    const user = userEvent.setup();
    renderPicker({ selected: [{ id: "1", name: "Machine Learning" }] });

    await user.type(screen.getByLabelText("Skills"), "a");

    expect(await screen.findByRole("button", { name: "Computer Vision" })).toBeInTheDocument();
    // The selected one appears only in the selection list, with a Remove button.
    expect(screen.queryByRole("button", { name: "Machine Learning" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Machine Learning" })).toBeInTheDocument();
  });

  it("removes a selected option", async () => {
    const user = userEvent.setup();
    const props = renderPicker({ selected: [{ id: "1", name: "Machine Learning" }] });

    await user.click(screen.getByRole("button", { name: "Remove Machine Learning" }));

    expect(props.onRemove).toHaveBeenCalledWith("1");
  });

  it("says so when nothing is selected", () => {
    renderPicker();

    expect(screen.getByText(/nothing selected yet/i)).toBeInTheDocument();
  });
});
