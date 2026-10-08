import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BEFORE_THE_OFFICE,
  DATE_LABEL,
  DISCLOSURE_WARNING,
  NOTE_REQUIRED,
  NUMBER_LABEL,
  officeLabel,
  STATUS_LABEL,
  VERIFICATION_LABEL,
} from "./labels";
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

describe("the disclosure pipeline", () => {
  it("labels every stage of the pipeline, university half and office half", () => {
    // The two halves are one pipeline on one record, so the labels have to
    // read as one sequence rather than as two vocabularies.
    expect(STATUS_LABEL.disclosed).toBe("Disclosed");
    expect(STATUS_LABEL.under_assessment).toBe("Under assessment");
    expect(STATUS_LABEL.approved_to_file).toBe("Approved to file");
    expect(STATUS_LABEL.declined).toBe("Not taken forward");
    expect(STATUS_LABEL.filed).toBe("Filed");
  });

  it("knows which stages are still inside the university", () => {
    // A record that has not been filed has no numbers to show, and the detail
    // page asks this before rendering the office's paperwork.
    for (const stage of [
      "disclosed",
      "under_assessment",
      "approved_to_file",
      "declined",
    ] as const) {
      expect(BEFORE_THE_OFFICE.has(stage)).toBe(true);
    }
    for (const stage of ["filed", "published", "granted", "lapsed"] as const) {
      expect(BEFORE_THE_OFFICE.has(stage)).toBe(false);
    }
  });

  it("requires a reason to decline, and only to decline", () => {
    // "No" without a reason is what stops the next person disclosing at all.
    expect(NOTE_REQUIRED.has("declined")).toBe(true);
    expect(NOTE_REQUIRED.has("approved_to_file")).toBe(false);
    expect(NOTE_REQUIRED.has("granted")).toBe(false);
  });

  it("names the date and number the office issues at each office stage", () => {
    expect(DATE_LABEL.filed).toBe("Filing date");
    expect(NUMBER_LABEL.granted).toBe("Grant number");
    // Nothing inside the university has either.
    expect(DATE_LABEL.disclosed).toBeUndefined();
    expect(NUMBER_LABEL.under_assessment).toBeUndefined();
  });

  it("warns about a public disclosure without pretending to give legal advice", () => {
    // Filing after a paper or poster is the commonest way a university loses
    // patent rights. The interface's job is to surface it while it can still
    // be acted on, and to send the question to the people who can answer it.
    expect(DISCLOSURE_WARNING).toMatch(/novelty/i);
    expect(DISCLOSURE_WARNING).toMatch(/differ sharply between patent offices/i);
    expect(DISCLOSURE_WARNING).toMatch(/IP cell/i);
  });
});
