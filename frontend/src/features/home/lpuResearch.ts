/**
 * Published research figures for Lovely Professional University.
 *
 * Every number here is a REAL figure taken from a public source, and every
 * one carries the source it came from -- this is a research-intelligence
 * product, and a statistic without a provenance is exactly what it exists to
 * argue against. Nothing in this file is derived from the prototype's own
 * demo data, and nothing in it may be invented: if a figure cannot be linked
 * to a source, it does not belong on the page.
 *
 * Two publication counts appear, deliberately. LPU publishes a Scopus-based
 * count and h-index; OpenAlex indexes a wider and differently-scoped corpus
 * and reports its own. They disagree because they are different databases
 * counting different things, not because one is wrong, so they are shown
 * side by side with their sources rather than blended into a single number
 * that would belong to neither.
 *
 * `RETRIEVED` is the date these were read. Figures marked "+" are stated
 * that way at the source and are reproduced as published.
 */

export const RETRIEVED = "8 October 2026";

export interface Source {
  label: string;
  url: string;
}

export const SOURCES = {
  lpuResearch: {
    label: "LPU — Research and Development",
    url: "https://www.lpu.in/academics/research.php",
  },
  lpuInnovations: {
    label: "LPU — Innovations",
    url: "https://www.lpu.in/innovations.php",
  },
  nirf: {
    label: "NIRF India Rankings 2025, as reported by LPU",
    url: "https://happenings.lpu.in/lpu-secures-31st-rank-among-all-government-and-private-universities-in-indias-nirf-rankings-2025/",
  },
  openAlex: {
    label: "OpenAlex — Lovely Professional University",
    url: "https://openalex.org/I110360157",
  },
} as const satisfies Record<string, Source>;

export interface Figure {
  value: string;
  label: string;
  note: string;
  source: Source;
}

/** The headline numbers, as published. */
export const HEADLINE_FIGURES: Figure[] = [
  {
    value: "34,363+",
    label: "Publications",
    note: "Indexed in Scopus",
    source: SOURCES.lpuResearch,
  },
  {
    value: "420,348+",
    label: "Citations",
    note: "Scopus, all years",
    source: SOURCES.lpuResearch,
  },
  {
    value: "3,200+",
    label: "IPR granted",
    note: "Patents and other intellectual property",
    source: SOURCES.lpuResearch,
  },
  {
    value: "₹98.35 cr+",
    label: "Funded projects",
    note: "Sponsored research funding",
    source: SOURCES.lpuResearch,
  },
  {
    value: "34",
    label: "In the world's top 2% of scientists",
    note: "Stanford University's 2024 list, up from 23 in 2023",
    source: SOURCES.lpuResearch,
  },
  {
    value: "550+",
    label: "Worldwide tie-ups",
    note: "International academic and industry partnerships",
    source: SOURCES.lpuResearch,
  },
];

export interface Ranking {
  discipline: string;
  rank: number;
}

/**
 * NIRF India Rankings 2025 -- the tenth edition, assessed across 17
 * categories on teaching and resources, research and professional practice,
 * graduation outcomes, outreach and inclusivity, and peer perception.
 * Ranks are among all institutions, government and private alike.
 */
export const NIRF_RANKINGS: Ranking[] = [
  { discipline: "Overall (universities)", rank: 31 },
  { discipline: "Pharmacy", rank: 13 },
  { discipline: "Agriculture & allied", rank: 17 },
  { discipline: "Architecture & planning", rank: 24 },
  { discipline: "Law", rank: 26 },
  { discipline: "Research institutions", rank: 40 },
  { discipline: "Management", rank: 44 },
  { discipline: "Engineering", rank: 48 },
];

export interface FieldStrength {
  field: string;
  works: number;
}

/**
 * Indexed works by field of research, from OpenAlex. This is what the
 * university actually publishes on, counted rather than claimed -- which is
 * the same question this platform asks of a department.
 */
export const FIELD_STRENGTHS: FieldStrength[] = [
  { field: "Engineering", works: 7156 },
  { field: "Computer science", works: 6148 },
  { field: "Agricultural & biological sciences", works: 4936 },
  { field: "Medicine", works: 2985 },
  { field: "Materials science", works: 2639 },
  { field: "Environmental science", works: 1633 },
  { field: "Biochemistry, genetics & molecular biology", works: 1624 },
  { field: "Social sciences", works: 1597 },
  { field: "Business & management", works: 1482 },
];

/** Figures OpenAlex reports for the institution as a whole. */
export const OPEN_ALEX_FIGURES: Figure[] = [
  {
    value: "38,230",
    label: "Works indexed",
    note: "30,786 of them published since 2021",
    source: SOURCES.openAlex,
  },
  {
    value: "837,325",
    label: "Citations received",
    note: "Across the indexed corpus",
    source: SOURCES.openAlex,
  },
  {
    value: "262",
    label: "h-index",
    note: "17,273 works cited at least ten times",
    source: SOURCES.openAlex,
  },
  {
    value: "41%",
    label: "Open access",
    note: "15,399 works free to read at the source",
    source: SOURCES.openAlex,
  },
];

export interface Facility {
  name: string;
  body: string;
  source: Source;
}

export const FACILITIES: Facility[] = [
  {
    name: "Central Instrumentation Facility",
    body: "A shared pool of high-end instruments, open to researchers across the schools rather than locked to one department.",
    source: SOURCES.lpuResearch,
  },
  {
    name: "Innovation Studio",
    body: "50,000 square feet holding nine specialised labs — ideation, artificial intelligence, prototyping, fabrication, metal casting, machining, machine diagnostics, paint and student projects.",
    source: SOURCES.lpuInnovations,
  },
  {
    name: "Research library",
    body: "29 million books and e-books, more than 41,000 journals and eleven online databases.",
    source: SOURCES.lpuResearch,
  },
];
