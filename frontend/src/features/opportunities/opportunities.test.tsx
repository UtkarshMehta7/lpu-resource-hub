import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApplyForm } from "./ApplyForm";
import { canApplyAs, REVIEWER_NEXT } from "./labels";

const { applyMock } = vi.hoisted(() => ({ applyMock: vi.fn() }));

vi.mock("./api", () => ({ applyToOpportunity: applyMock }));

describe("canApplyAs", () => {
  it("lets students apply to student openings only", () => {
    expect(canApplyAs("student", "research_assistant")).toBe(true);
    expect(canApplyAs("student", "collaboration")).toBe(false);
  });

  it("lets faculty and coordinators apply to collaborations only", () => {
    expect(canApplyAs("faculty", "collaboration")).toBe(true);
    expect(canApplyAs("research_coordinator", "collaboration")).toBe(true);
    expect(canApplyAs("faculty", "research_internship")).toBe(false);
    expect(canApplyAs("admin", "collaboration")).toBe(false);
  });
});

describe("REVIEWER_NEXT", () => {
  it("never offers a decision on final statuses", () => {
    expect(REVIEWER_NEXT.accepted).toEqual([]);
    expect(REVIEWER_NEXT.rejected).toEqual([]);
    expect(REVIEWER_NEXT.withdrawn).toEqual([]);
    expect(REVIEWER_NEXT.submitted).not.toContain("accepted");
  });
});

describe("ApplyForm", () => {
  it("requires a meaningful statement before submitting", async () => {
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ApplyForm opportunityId="o1" />
      </QueryClientProvider>,
    );

    await user.type(screen.getByLabelText(/good fit/i), "Too short");
    await user.click(screen.getByRole("button", { name: /submit application/i }));

    expect(await screen.findByText(/at least 20 characters/i)).toBeInTheDocument();
    expect(applyMock).not.toHaveBeenCalled();
  });

  it("submits the trimmed statement", async () => {
    const user = userEvent.setup();
    applyMock.mockResolvedValue({});
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ApplyForm opportunityId="o1" />
      </QueryClientProvider>,
    );

    await user.type(screen.getByLabelText(/good fit/i), "  I have built soil sensors before.  ");
    await user.click(screen.getByRole("button", { name: /submit application/i }));

    await vi.waitFor(() =>
      expect(applyMock).toHaveBeenCalledWith("o1", "I have built soil sensors before."),
    );
  });
});
