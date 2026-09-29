import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InstitutionalReportPage } from "./InstitutionalReportPage";
import type { AcademicYearOption, InstitutionalReport } from "./api";

const fetchAcademicYears = vi.fn<() => Promise<AcademicYearOption[]>>();
const fetchInstitutionalReport = vi.fn<(year: string) => Promise<InstitutionalReport>>();
const downloadInstitutionalReport = vi.fn<(year: string, format: "csv" | "pdf") => Promise<void>>();

vi.mock("./api", () => ({
  fetchAcademicYears: () => fetchAcademicYears(),
  fetchInstitutionalReport: (year: string) => fetchInstitutionalReport(year),
  downloadInstitutionalReport: (year: string, format: "csv" | "pdf") =>
    downloadInstitutionalReport(year, format),
}));

const YEARS: AcademicYearOption[] = [
  { label: "2026-27", start: "2026-07-01", end: "2027-06-30", is_current: true },
  { label: "2025-26", start: "2025-07-01", end: "2026-06-30", is_current: false },
];

const REPORT: InstitutionalReport = {
  academic_year: "2026-27",
  period_start: "2026-07-01",
  period_end: "2027-06-30",
  generated_at: "2026-09-29 08:00 UTC",
  scope: "the whole institution",
  sections: [
    {
      title: "Research opportunities",
      summary: [
        ["Decided", "2"],
        ["Success rate", "not applicable"],
      ],
      tables: [
        {
          title: "Application outcomes",
          columns: ["Outcome", "Applications"],
          rows: [
            ["Accepted", "1"],
            ["Rejected", "1"],
          ],
          definition: "success rate = accepted / (accepted + rejected).",
        },
      ],
    },
    {
      title: "Publications",
      summary: [],
      tables: [
        {
          title: "Publications by year",
          columns: ["Year", "Publications"],
          rows: [],
          definition: null,
        },
      ],
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <InstitutionalReportPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchAcademicYears.mockReset();
  fetchInstitutionalReport.mockReset();
  downloadInstitutionalReport.mockReset();
  fetchAcademicYears.mockResolvedValue(YEARS);
  fetchInstitutionalReport.mockResolvedValue(REPORT);
  downloadInstitutionalReport.mockResolvedValue(undefined);
});

describe("InstitutionalReportPage", () => {
  it("opens on the current academic year without being asked", async () => {
    renderPage();
    expect(await screen.findByText(/2026-07-01 to 2027-06-30/)).toBeInTheDocument();
    expect(fetchInstitutionalReport).toHaveBeenCalledWith("2026-27");
  });

  it("shows each figure with the rule that produced it", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Application outcomes" });
    expect(
      screen.getByText(/success rate = accepted \/ \(accepted \+ rejected\)/),
    ).toBeInTheDocument();
  });

  it("says 'not applicable' rather than inventing a zero", async () => {
    renderPage();
    expect(await screen.findByText("not applicable")).toBeInTheDocument();
  });

  it("says plainly when a table has nothing in it", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Publications by year" });
    expect(screen.getByText("No records in this period.")).toBeInTheDocument();
  });

  it("reloads when another year is chosen", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Application outcomes" });

    await user.selectOptions(screen.getByLabelText("Academic year"), "2025-26");
    expect(fetchInstitutionalReport).toHaveBeenCalledWith("2025-26");
  });

  it("downloads each format through the authenticated client", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Application outcomes" });

    await user.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(downloadInstitutionalReport).toHaveBeenCalledWith("2026-27", "csv");

    await user.click(screen.getByRole("button", { name: "Download PDF" }));
    expect(downloadInstitutionalReport).toHaveBeenCalledWith("2026-27", "pdf");
  });

  it("reports a failed download instead of appearing to succeed", async () => {
    const user = userEvent.setup();
    downloadInstitutionalReport.mockRejectedValue(new Error("nope"));
    renderPage();
    await screen.findByRole("heading", { name: "Application outcomes" });

    await user.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("renders the tables as real tables, for a screen reader", async () => {
    renderPage();
    const table = await screen.findByRole("table", { name: "Application outcomes" });
    expect(within(table).getByRole("columnheader", { name: "Outcome" })).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });
});
