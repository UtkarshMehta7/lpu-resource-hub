import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  FACILITIES,
  FIELD_STRENGTHS,
  HEADLINE_FIGURES,
  NIRF_RANKINGS,
  OPEN_ALEX_FIGURES,
  SOURCES,
} from "./lpuResearch";
import { ResearchShowcase } from "./ResearchShowcase";

describe("ResearchShowcase", () => {
  it("shows the published figures and the rankings", () => {
    render(<ResearchShowcase />);

    expect(screen.getByText("34,363+")).toBeInTheDocument();
    expect(screen.getByText("₹98.35 cr+")).toBeInTheDocument();
    expect(screen.getByText("#31")).toBeInTheDocument();
    expect(screen.getByText("Research institutions")).toBeInTheDocument();
    // "Engineering" is both a NIRF discipline and an OpenAlex field, so it is
    // legitimately on the page twice; the bar is what makes it the field.
    expect(
      screen.getByRole("img", { name: /^Engineering: 7,156 indexed works$/ }),
    ).toBeInTheDocument();
  });

  it("links every figure group to the source it came from", () => {
    // A statistic without a provenance is the thing this product argues
    // against, so the sources are part of the section, not a footnote we may
    // quietly drop.
    render(<ResearchShowcase />);

    for (const source of Object.values(SOURCES)) {
      expect(screen.getByRole("link", { name: new RegExp(source.label, "i") })).toHaveAttribute(
        "href",
        source.url,
      );
    }
  });

  it("says plainly that these are not the prototype's own records", () => {
    // The platform is not an official LPU system and its own data is
    // fictional. Real published figures sitting beside demo data must never
    // be readable as the demo data's output.
    render(<ResearchShowcase />);

    const provenance = screen.getByText(
      (_, element) =>
        element?.tagName === "P" &&
        /not records held in this prototype/i.test(element.textContent ?? ""),
    );
    expect(within(provenance).getByText("not")).toBeInTheDocument();
    expect(provenance).toHaveTextContent(/fictional demo data/i);
  });

  it("draws the widest field at full width and the rest in proportion", () => {
    render(<ResearchShowcase />);

    // reduce without a seed is typed as the element, so this needs no index
    // access -- noUncheckedIndexedAccess rejects FIELD_STRENGTHS[0].
    const busiest = FIELD_STRENGTHS.reduce((a, b) => (b.works > a.works ? b : a));
    const bar = screen.getByRole("img", { name: new RegExp(`^${busiest.field}:`, "i") });
    expect(bar.firstElementChild).toHaveStyle({ width: "100%" });
  });

  it("renders every entry it was given", () => {
    render(<ResearchShowcase />);

    for (const figure of [...HEADLINE_FIGURES, ...OPEN_ALEX_FIGURES]) {
      expect(screen.getByText(figure.label)).toBeInTheDocument();
    }
    for (const facility of FACILITIES) {
      expect(screen.getByText(facility.name)).toBeInTheDocument();
    }
    expect(screen.getAllByText(/^#\d+$/)).toHaveLength(NIRF_RANKINGS.length);
  });
});
