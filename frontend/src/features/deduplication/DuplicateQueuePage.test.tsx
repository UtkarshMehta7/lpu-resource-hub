import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DuplicateQueuePage } from "./DuplicateQueuePage";
import type { DuplicateReview } from "./types";

const { fetchDuplicates, scanForDuplicates, decideDuplicate, undoDuplicateMerge } = vi.hoisted(
  () => ({
    fetchDuplicates: vi.fn(),
    scanForDuplicates: vi.fn(),
    decideDuplicate: vi.fn(),
    undoDuplicateMerge: vi.fn(),
  }),
);

vi.mock("./api", () => ({
  fetchDuplicates,
  scanForDuplicates,
  decideDuplicate,
  undoDuplicateMerge,
}));

const PAIR: DuplicateReview = {
  id: "r1",
  status: "suspected",
  score: 97.5,
  evidence: {
    title_similarity: 97.5,
    identical_normalised_title: false,
    same_year: true,
    years: [2024, 2024],
    shared_doi: false,
    doi_on_one_side_only: true,
    same_venue: true,
    shared_authors: ["a singh"],
    shared_author_count: 1,
  },
  publication_a: {
    id: "pa",
    title: "Forecasting wheat yield from satellite data",
    doi: null,
    url: null,
    venue: "Journal of Agritech",
    year: 2024,
    pub_type: "journal_article",
    authors: ["A Singh"],
    project_count: 1,
    created_at: "2026-01-01T00:00:00Z",
  },
  publication_b: {
    id: "pb",
    title: "Forecasting wheat yield from satellite data.",
    doi: "10.1000/wheat",
    url: null,
    venue: "Journal of Agritech",
    year: 2024,
    pub_type: "journal_article",
    authors: ["A Singh", "B Kaur"],
    project_count: 0,
    created_at: "2026-02-01T00:00:00Z",
  },
  merged_into_id: null,
  can_undo: false,
  decided_by: null,
  decided_by_name: null,
  decided_at: null,
  decision_note: null,
  created_at: "2026-03-01T00:00:00Z",
};

function page<T>(items: T[]) {
  return { items, page: 1, page_size: 20, total: items.length };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DuplicateQueuePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDuplicates.mockResolvedValue(page([PAIR]));
  scanForDuplicates.mockResolvedValue({
    examined: 12,
    pairs_found: 1,
    pairs_new: 1,
    pairs_already_decided: 0,
  });
  decideDuplicate.mockResolvedValue({ ...PAIR, status: "merged" });
  undoDuplicateMerge.mockResolvedValue({ ...PAIR, status: "suspected" });
});

describe("DuplicateQueuePage", () => {
  it("shows both records in full, with the DOI as a link to check it", async () => {
    renderPage();

    expect(
      await screen.findByText("Forecasting wheat yield from satellite data"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "10.1000/wheat" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/wheat",
    );
    // The cost of merging has to be visible before deciding.
    expect(screen.getByText("Linked to 1 project")).toBeInTheDocument();
  });

  it("says in words why the pair was suggested, not just a score", async () => {
    renderPage();

    const reason = await screen.findByText(/Suggested because/);
    expect(reason).toHaveTextContent("Titles 98% alike");
    expect(reason).toHaveTextContent("same year");
    expect(reason).toHaveTextContent("only one side has a DOI");
    expect(reason).toHaveTextContent("1 author in common");
  });

  it("merges into whichever record the reviewer keeps", async () => {
    const user = userEvent.setup();
    renderPage();

    const buttons = await screen.findAllByRole("button", { name: "Keep this one" });
    expect(buttons).toHaveLength(2);
    await user.click(buttons[1]!);

    // The second card is record B, so B survives.
    await waitFor(() =>
      expect(decideDuplicate).toHaveBeenCalledWith("r1", "merge", { keep_id: "pb" }),
    );
  });

  it("records a judgement that the two are different works", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Mark as different" }));

    await waitFor(() => expect(decideDuplicate).toHaveBeenCalledWith("r1", "separate", {}));
  });

  it("can set a pair aside without claiming a judgement", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Decide later" }));

    await waitFor(() => expect(decideDuplicate).toHaveBeenCalledWith("r1", "ignore", {}));
  });

  it("offers undo only on a merge that still has its snapshot", async () => {
    fetchDuplicates.mockResolvedValue(
      page([{ ...PAIR, status: "merged", can_undo: true, merged_into_id: "pa" }]),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Undo merge" }));

    await waitFor(() => expect(undoDuplicateMerge).toHaveBeenCalledWith("r1"));
  });

  it("says plainly when a merge can no longer be undone", async () => {
    fetchDuplicates.mockResolvedValue(page([{ ...PAIR, status: "merged", can_undo: false }]));
    renderPage();

    expect(await screen.findByText(/can no longer be undone/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo merge" })).not.toBeInTheDocument();
  });

  it("reports what a scan examined and found", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Scan for duplicates" }));

    expect(await screen.findByText(/Examined 12 publications/)).toBeInTheDocument();
  });

  it("offers nothing to decide on a pair that was already decided", async () => {
    fetchDuplicates.mockResolvedValue(
      page([{ ...PAIR, status: "separate", decided_by_name: "Demo Admin" }]),
    );
    renderPage();

    await screen.findByText("Decided by Demo Admin");
    expect(screen.queryByRole("button", { name: "Keep this one" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as different" })).not.toBeInTheDocument();
  });

  it("says plainly when a record on one side is gone", async () => {
    fetchDuplicates.mockResolvedValue(
      page([{ ...PAIR, status: "merged", publication_b: null, merged_into_id: "pa" }]),
    );
    renderPage();

    expect(await screen.findByText(/Record B: this record no longer exists/)).toBeInTheDocument();
  });
});
