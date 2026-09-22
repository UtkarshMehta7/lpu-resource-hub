import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportButton } from "./ReportButton";

const { reportMock } = vi.hoisted(() => ({ reportMock: vi.fn() }));

vi.mock("./api", () => ({ reportContent: reportMock }));

beforeAll(() => {
  // jsdom doesn't implement <dialog>.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
  };
});

describe("ReportButton", () => {
  beforeEach(() => reportMock.mockReset());

  it("requires a real explanation before reporting", async () => {
    const user = userEvent.setup();
    render(<ReportButton targetType="project" targetId="p1" />);

    await user.click(screen.getByRole("button", { name: /^report$/i }));
    await user.type(screen.getByLabelText(/what's wrong/i), "bad");
    await user.click(screen.getByRole("button", { name: /send report/i, hidden: true }));

    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(reportMock).not.toHaveBeenCalled();
  });

  it("sends the report and then disables itself", async () => {
    const user = userEvent.setup();
    reportMock.mockResolvedValue({});
    render(<ReportButton targetType="publication" targetId="pub1" />);

    await user.click(screen.getByRole("button", { name: /^report$/i }));
    await user.type(screen.getByLabelText(/what's wrong/i), "  This looks like spam content.  ");
    await user.click(screen.getByRole("button", { name: /send report/i, hidden: true }));

    await vi.waitFor(() =>
      expect(reportMock).toHaveBeenCalledWith({
        target_type: "publication",
        target_id: "pub1",
        reason: "This looks like spam content.",
      }),
    );
    expect(await screen.findByRole("button", { name: /reported/i })).toBeDisabled();
  });
});
