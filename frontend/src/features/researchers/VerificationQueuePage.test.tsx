import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VerificationQueuePage } from "./VerificationQueuePage";

const { fetchVerificationQueue, decideVerification } = vi.hoisted(() => ({
  fetchVerificationQueue: vi.fn(),
  decideVerification: vi.fn(),
}));

vi.mock("./api", () => ({ fetchVerificationQueue, decideVerification }));

function renderPage() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <VerificationQueuePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchVerificationQueue.mockResolvedValue([
    {
      user_id: "u7",
      full_name: "Neha Gupta",
      registration_number: "12400112",
      email: "neha@example.edu",
      designation: "Assistant Professor",
      department_id: "d1",
      verification_status: "pending",
      created_at: "2026-09-24T10:00:00Z",
    },
  ]);
});

describe("VerificationQueuePage", () => {
  it("links each person waiting to their profile", async () => {
    // Deciding on somebody without being able to read their profile first is
    // guesswork.
    renderPage();

    const link = await screen.findByRole("link", { name: "Neha Gupta" });
    expect(link).toHaveAttribute("href", "/researchers/u7");
  });

  it("still shows the UID and designation beside the name", async () => {
    renderPage();

    expect(await screen.findByText("12400112")).toBeInTheDocument();
    expect(screen.getByText("Assistant Professor")).toBeInTheDocument();
  });
});
