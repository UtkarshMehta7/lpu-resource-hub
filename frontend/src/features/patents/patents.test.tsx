import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { STATUS_LABEL, officeLabel, VERIFICATION_LABEL } from "./labels";
import { PriorArtPanel } from "./PriorArtPanel";
import type { PriorArtResult } from "./types";

const { searchMock } = vi.hoisted(() => ({ searchMock: vi.fn() }));

vi.mock("./api", () => ({ searchPriorArt: searchMock }));

const REGISTRIES = [
  { name: "Espacenet", description: "EPO worldwide collection.", url: "https://e/?q=robot" },
  { name: "Google Patents", description: "100+ offices.", url: "https://g/?q=robot" },
  { name: "WIPO PATENTSCOPE", description: "PCT applications.", url: "https://w/?q=robot" },
  { name: "InPASS (India)", description: "Indian Patent Office.", url: "https://i/" },
];

function result(overrides: Partial<PriorArtResult> = {}): PriorArtResult {
  return {
    searched: "A borewell rescue robot",
    similar_patents: [],
    related_works: [],
    registries: REGISTRIES,
    literature_unavailable: false,
    ...overrides,
  };
}

function renderPanel(title = "A borewell rescue robot") {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <PriorArtPanel title={title} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PriorArtPanel", () => {
  beforeEach(() => {
    searchMock.mockReset();
  });

  it("never implies the world has been searched", async () => {
    // No open API covers worldwide patents. An empty result here means "two
    // open indexes found nothing", not "this invention is novel", and saying
    // otherwise would be the most harmful thing this feature could do.
    searchMock.mockResolvedValue(result());
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /check prior art/i }));

    // The disclaimer emphasises "not" with an <em>, so the sentence is split
    // across elements and a plain string matcher would miss it.
    const disclaimer = await screen.findByText(
      (_, element) =>
        element?.tagName === "H3" && /has not searched the world/i.test(element.textContent ?? ""),
    );
    expect(disclaimer).toBeInTheDocument();
    for (const registry of REGISTRIES) {
      // "InPASS (India)" has parentheses, which a bare RegExp would read as a
      // capture group and match "InPASSIndia" instead.
      // The accessible name is the whole card (title + description), and
      // "InPASS (India)" has parentheses a bare RegExp would read as a group.
      expect(
        screen.getByRole("link", { name: (accessible) => accessible.includes(registry.name) }),
      ).toHaveAttribute("href", registry.url);
    }
  });

  it("says when a literature index was unreachable", async () => {
    // A short list presented as a clean result reads as "nothing like this
    // exists", which is the opposite of what happened.
    searchMock.mockResolvedValue(result({ literature_unavailable: true }));
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /check prior art/i }));

    expect(
      await screen.findByText(/could not be reached, so this list is incomplete/i),
    ).toBeInTheDocument();
  });

  it("surfaces a patent already recorded here, with how alike it is", async () => {
    searchMock.mockResolvedValue(
      result({
        similar_patents: [
          {
            id: "p1",
            title: "A borewell rescue robot with a self-centring gripper",
            jurisdiction: "IN",
            status: "granted",
            filing_date: "2024-01-01",
            grant_number: "IN445566",
            score: 93.4,
          },
        ],
      }),
    );
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /check prior art/i }));

    const link = await screen.findByRole("link", { name: /self-centring gripper/i });
    expect(link).toHaveAttribute("href", "/patents/p1");
    expect(screen.getByText(/93.4% alike/)).toBeInTheDocument();
    expect(screen.getByText(STATUS_LABEL.granted)).toBeInTheDocument();
  });

  it("links published literature out to its DOI", async () => {
    searchMock.mockResolvedValue(
      result({
        related_works: [
          {
            title: "A tracked robot for borewell child rescue",
            venue: "Journal of Field Robotics",
            year: 2019,
            doi: "10.1000/robot",
            url: "https://doi.org/10.1000/robot",
            source: "OpenAlex",
          },
        ],
      }),
    );
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /check prior art/i }));

    expect(await screen.findByRole("link", { name: /tracked robot/i })).toHaveAttribute(
      "href",
      "https://doi.org/10.1000/robot",
    );
  });

  it("will not run without a title to search on", async () => {
    renderPanel("");

    expect(screen.getByRole("button", { name: /check prior art/i })).toBeDisabled();
    expect(screen.getByText(/give the patent a title first/i)).toBeInTheDocument();
    await waitFor(() => expect(searchMock).not.toHaveBeenCalled());
  });

  it("keeps the registry links usable when the check itself fails", async () => {
    searchMock.mockRejectedValue(new Error("offline"));
    renderPanel();

    await userEvent.click(screen.getByRole("button", { name: /check prior art/i }));

    expect(await screen.findByText(/registry links below still work/i)).toBeInTheDocument();
  });
});

describe("labels", () => {
  it("names the office but keeps its code, which is what a reader checks", () => {
    expect(officeLabel("IN")).toBe("India (IN)");
    expect(officeLabel("EP")).toBe("European Patent Office (EP)");
    // An office we have no name for still renders, rather than showing blank.
    expect(officeLabel("ZZ")).toBe("ZZ");
  });

  it("keeps the office's verdict and the university's apart", () => {
    // Showing these in one pill would say a coordinator's approval and a
    // patent grant were the same event.
    expect(STATUS_LABEL.granted).toBe("Granted");
    expect(VERIFICATION_LABEL.verified).toBe("Verified");
    expect(VERIFICATION_LABEL.pending).toBe("Awaiting review");
  });
});
