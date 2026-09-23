import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { totalResults, type SearchResults } from "./api";
import { SearchPage } from "./SearchPage";

const { lexicalMock, semanticMock } = vi.hoisted(() => ({
  lexicalMock: vi.fn(),
  semanticMock: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<{ totalResults: typeof totalResults }>();
  return { ...actual, searchLexical: lexicalMock, searchSemantic: semanticMock };
});

function results(overrides: Partial<SearchResults> = {}): SearchResults {
  return {
    query: "soil sensing",
    researchers: [],
    projects: [],
    publications: [],
    opportunities: [],
    ...overrides,
  };
}

const PROJECT = {
  id: "p1",
  title: "Low-cost soil sensors",
  summary: "s",
  status: "active" as const,
  owner_id: "u1",
  owner_name: "Dr. Demo",
  owner_registration_number: "DEMOFACULTY07",
  department_id: null,
  start_date: null,
  end_date: null,
  research_areas: [],
  skills: [],
};

function renderPage(initial = "/search?q=soil+sensing") {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[initial]}>
        <SearchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("totalResults", () => {
  it("counts every kind of match", () => {
    expect(totalResults(undefined)).toBe(0);
    expect(totalResults(results())).toBe(0);
    expect(totalResults(results({ projects: [PROJECT] }))).toBe(1);
  });
});

describe("SearchPage", () => {
  beforeEach(() => {
    lexicalMock.mockReset();
    semanticMock.mockReset();
  });

  it("uses smart search by default and shows the matches", async () => {
    semanticMock.mockResolvedValue(results({ projects: [PROJECT], semantic_used: true }));
    renderPage();

    expect(await screen.findByText("Low-cost soil sensors")).toBeInTheDocument();
    expect(semanticMock).toHaveBeenCalledWith("soil sensing");
    expect(lexicalMock).not.toHaveBeenCalled();
    expect(screen.getByText(/1 match for/)).toBeInTheDocument();
  });

  it("switches to keyword search when asked", async () => {
    const user = userEvent.setup();
    semanticMock.mockResolvedValue(results());
    lexicalMock.mockResolvedValue(results({ projects: [PROJECT] }));
    renderPage();

    await user.click(screen.getByRole("button", { name: "Keyword" }));

    await vi.waitFor(() => expect(lexicalMock).toHaveBeenCalledWith("soil sensing"));
    expect(await screen.findByText("Low-cost soil sensors")).toBeInTheDocument();
  });

  it("says so when the server can't do smart search", async () => {
    semanticMock.mockResolvedValue(results({ projects: [PROJECT], semantic_used: false }));
    renderPage();

    expect(await screen.findByText(/isn't available on this server/i)).toBeInTheDocument();
  });

  it("offers examples before anything is searched", () => {
    renderPage("/search");

    expect(screen.getByText("Try a question")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /researchers working on soil moisture sensing/i }),
    ).toBeInTheDocument();
    expect(semanticMock).not.toHaveBeenCalled();
  });

  it("suggests what to do when nothing matches", async () => {
    semanticMock.mockResolvedValue(results());
    renderPage();

    expect(await screen.findByText("Nothing found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /browse researchers/i })).toBeInTheDocument();
  });
});
