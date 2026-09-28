import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ImportProfilePanel } from "./ImportProfilePanel";
import type { AuthorCandidate, ImportLookup, ImportPreview, ImportResult } from "./types";

// Typed explicitly: an untyped vi.fn() returns `any`, which the lint rules
// (rightly) refuse to let through into the component under test.
const previewProfileImport = vi.fn<(lookup: ImportLookup) => Promise<ImportPreview>>();
const searchImportCandidates =
  vi.fn<(name: string, affiliation?: string | null) => Promise<AuthorCandidate[]>>();
const fetchImportHistory = vi.fn<() => Promise<never[]>>();
const applyProfileImport =
  vi.fn<
    (lookup: ImportLookup & { fields: string[]; work_keys: string[] }) => Promise<ImportResult>
  >();

vi.mock("./api", () => ({
  previewProfileImport: (lookup: ImportLookup) => previewProfileImport(lookup),
  searchImportCandidates: (name: string) => searchImportCandidates(name),
  fetchImportHistory: () => fetchImportHistory(),
  applyProfileImport: (lookup: ImportLookup & { fields: string[]; work_keys: string[] }) =>
    applyProfileImport(lookup),
}));

const PREVIEW: ImportPreview = {
  orcid: "0000-0002-1825-0097",
  sources_used: ["orcid", "openalex"],
  source_errors: { semantic_scholar: "Semantic Scholar was busy." },
  source_urls: {},
  full_name: "A. Sharma",
  affiliation: "Lovely Professional University",
  metrics: { h_index: 12 },
  fields: [
    { field: "bio", current: "Old bio", incoming: "New bio", changed: true },
    { field: "designation", current: "Professor", incoming: "Professor", changed: false },
  ],
  topics: ["Soil Science"],
  works: [
    {
      key: "doi:10.1/new",
      title: "A brand new paper",
      doi: "10.1/new",
      venue: "Journal of Soil Science",
      year: 2024,
      pub_type: "journal_article",
      abstract: null,
      url: "https://doi.org/10.1/new",
      authors: ["A. Sharma"],
      sources: ["orcid"],
      status: "new",
      matched_publication_id: null,
      matched_title: null,
      similarity: null,
      reason: null,
      importable: true,
    },
    {
      key: "doi:10.1/known",
      title: "Something already saved",
      doi: "10.1/known",
      venue: null,
      year: 2020,
      pub_type: "journal_article",
      abstract: null,
      url: null,
      authors: [],
      sources: ["openalex"],
      status: "already_in_register",
      matched_publication_id: "abc",
      matched_title: "Something already saved",
      similarity: 100,
      reason: "Already in the register, matched on DOI.",
      importable: false,
    },
    {
      key: "title:a close one",
      title: "A close one",
      doi: null,
      venue: null,
      year: 2019,
      pub_type: "other",
      abstract: null,
      url: null,
      authors: [],
      sources: ["openalex"],
      status: "possible_duplicate",
      matched_publication_id: "def",
      matched_title: "A close one indeed",
      similarity: 88,
      reason: "Looks close to an existing entry (88%) -- please check.",
      importable: true,
    },
  ],
  new_count: 1,
  known_count: 1,
};

function candidate(overrides: Partial<AuthorCandidate> = {}): AuthorCandidate {
  return {
    source: "openalex",
    source_id: "A1",
    source_url: "https://openalex.org/A1",
    full_name: "Nitish Kumar",
    affiliation: "Lovely Professional University",
    other_affiliations: [],
    orcid: null,
    works_count: 12,
    cited_by_count: 30,
    h_index: 4,
    topics: ["Soil Science"],
    ...overrides,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ImportProfilePanel linkedOrcid={null} onImported={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("ImportProfilePanel", () => {
  beforeEach(() => {
    previewProfileImport.mockReset();
    applyProfileImport.mockReset();
    searchImportCandidates.mockReset();
    fetchImportHistory.mockReset();
    fetchImportHistory.mockResolvedValue([]);
  });

  it("will not look anything up until given an ORCID iD or a name", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: "Look me up" })).toBeDisabled();
  });

  it("shows what was found and pre-ticks only the genuinely new work", async () => {
    const user = userEvent.setup();
    previewProfileImport.mockResolvedValue(PREVIEW);
    renderPanel();

    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0097");
    await user.click(screen.getByRole("button", { name: "Look me up" }));

    // Anchored on the summary line: the researcher's name also appears in an
    // author list, so it is not a unique handle.
    expect(await screen.findByText(/1 new, 1 already saved/)).toBeInTheDocument();

    // A source that failed is reported rather than hidden.
    expect(screen.getByText(/Semantic Scholar was busy/)).toBeInTheDocument();

    // New work is ticked; a possible duplicate needs a human decision, so it
    // is offered but not ticked; work already saved cannot be ticked at all.
    expect(screen.getByLabelText("Import A brand new paper")).toBeChecked();
    expect(screen.getByLabelText("Import A close one")).not.toBeChecked();
    expect(screen.getByLabelText("Import Something already saved")).toBeDisabled();
  });

  it("offers only the profile fields that would actually change", async () => {
    const user = userEvent.setup();
    previewProfileImport.mockResolvedValue(PREVIEW);
    renderPanel();

    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0097");
    await user.click(screen.getByRole("button", { name: "Look me up" }));
    await screen.findByText(/1 new, 1 already saved/);

    const fields = screen.getByRole("group", { name: "Profile details" });
    expect(within(fields).getByText("Biography")).toBeInTheDocument();
    expect(within(fields).queryByText("Designation")).not.toBeInTheDocument();
  });

  it("imports only the ticked items", async () => {
    const user = userEvent.setup();
    previewProfileImport.mockResolvedValue(PREVIEW);
    applyProfileImport.mockResolvedValue({
      import_id: "1",
      applied_fields: ["bio"],
      works_imported: 1,
      works_skipped: 0,
      works_failed: 0,
      source_errors: {},
      verification_reset: false,
    });
    renderPanel();

    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0097");
    await user.click(screen.getByRole("button", { name: "Look me up" }));
    await screen.findByText(/1 new, 1 already saved/);

    await user.click(screen.getByRole("button", { name: /Import 2 selected/ }));

    expect(applyProfileImport).toHaveBeenCalledWith(
      expect.objectContaining({
        orcid: "0000-0002-1825-0097",
        fields: ["bio"],
        work_keys: ["doi:10.1/new"],
      }),
    );
    expect(await screen.findByText(/Imported 1 publication\./)).toBeInTheDocument();
  });

  it("reports an error instead of pretending the import worked", async () => {
    const user = userEvent.setup();
    previewProfileImport.mockRejectedValue(new Error("boom"));
    renderPanel();

    await user.type(screen.getByLabelText("ORCID iD"), "bad");
    await user.click(screen.getByRole("button", { name: "Look me up" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("choosing between namesakes", () => {
  it("offers candidates instead of guessing when only a name is given", async () => {
    const user = userEvent.setup();
    searchImportCandidates.mockResolvedValue([
      candidate({ source_id: "A1", full_name: "Nitish Srivastava", affiliation: "Google" }),
      candidate({ source_id: "A2", full_name: "Nitish Kumar", affiliation: "SRM Institute" }),
    ]);
    renderPanel();

    await user.type(screen.getByLabelText("or your published name"), "Nitish Kumar");
    await user.click(screen.getByRole("button", { name: "Look me up" }));

    expect(await screen.findByText(/Which of these is you\?/)).toBeInTheDocument();
    expect(screen.getByText("Nitish Srivastava")).toBeInTheDocument();
    expect(screen.getByText("Nitish Kumar")).toBeInTheDocument();
    // Nothing was imported or previewed off the back of a name alone.
    expect(previewProfileImport).not.toHaveBeenCalled();
  });

  it("links each candidate to the record so the choice can be checked", async () => {
    const user = userEvent.setup();
    searchImportCandidates.mockResolvedValue([candidate()]);
    renderPanel();

    await user.type(screen.getByLabelText("or your published name"), "Nitish Kumar");
    await user.click(screen.getByRole("button", { name: "Look me up" }));

    const link = await screen.findByRole("link", { name: /Open the record to check/ });
    expect(link).toHaveAttribute("href", "https://openalex.org/A1");
  });

  it("previews only the candidate the researcher picked", async () => {
    const user = userEvent.setup();
    searchImportCandidates.mockResolvedValue([candidate({ source_id: "A2" })]);
    previewProfileImport.mockResolvedValue(PREVIEW);
    renderPanel();

    await user.type(screen.getByLabelText("or your published name"), "Nitish Kumar");
    await user.click(screen.getByRole("button", { name: "Look me up" }));
    await user.click(await screen.findByRole("button", { name: "This is me" }));

    expect(previewProfileImport).toHaveBeenCalledWith(
      expect.objectContaining({ openalex_author_id: "A2" }),
    );
  });

  it("says so plainly when nobody matches", async () => {
    const user = userEvent.setup();
    searchImportCandidates.mockResolvedValue([]);
    renderPanel();

    await user.type(screen.getByLabelText("or your published name"), "Nobody At All");
    await user.click(screen.getByRole("button", { name: "Look me up" }));

    expect(await screen.findByText(/No researcher on OpenAlex matches/)).toBeInTheDocument();
  });

  it("links a publication to its DOI so it can be verified before importing", async () => {
    const user = userEvent.setup();
    previewProfileImport.mockResolvedValue(PREVIEW);
    renderPanel();

    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0097");
    await user.click(screen.getByRole("button", { name: "Look me up" }));
    await screen.findByText(/1 new, 1 already saved/);

    const title = screen.getByRole("link", { name: "A brand new paper" });
    expect(title).toHaveAttribute("href", "https://doi.org/10.1/new");
  });

  it("says when an import sent the profile back for verification", async () => {
    const user = userEvent.setup();
    previewProfileImport.mockResolvedValue(PREVIEW);
    applyProfileImport.mockResolvedValue({
      import_id: "1",
      applied_fields: ["bio"],
      works_imported: 1,
      works_skipped: 0,
      works_failed: 0,
      source_errors: {},
      verification_reset: true,
    });
    renderPanel();

    await user.type(screen.getByLabelText("ORCID iD"), "0000-0002-1825-0097");
    await user.click(screen.getByRole("button", { name: "Look me up" }));
    await screen.findByText(/1 new, 1 already saved/);
    await user.click(screen.getByRole("button", { name: /Import 2 selected/ }));

    expect(await screen.findByText(/back to your department coordinator/)).toBeInTheDocument();
  });
});
