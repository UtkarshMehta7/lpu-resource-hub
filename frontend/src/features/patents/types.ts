/**
 * Hand-written mirrors of the backend's Pydantic schemas.
 *
 * These have drifted twice before, so they are written in the same change as
 * the schemas they mirror -- see backend/app/modules/patents/schemas.py.
 */

/**
 * Where the invention has got to, from disclosure through to grant.
 *
 * The first four are the UNIVERSITY's: an inventor discloses, the IP cell
 * assesses, and the university decides whether to file. The rest are the
 * patent office's. One pipeline, because it is one invention.
 */
export type PatentStatus =
  | "disclosed"
  | "under_assessment"
  | "approved_to_file"
  | "declined"
  | "filed"
  | "published"
  | "granted"
  | "lapsed"
  | "rejected"
  | "withdrawn";

/** Reused from the researcher profiles: the same four words mean the same thing. */
export type VerificationStatus = "unverified" | "pending" | "verified" | "rejected";

export interface Inventor {
  user_id: string | null;
  name: string;
  registration_number: string | null;
  inventor_order: number;
}

export interface LinkedProject {
  id: string;
  title: string;
}

export interface Patent {
  id: string;
  title: string;
  abstract: string | null;
  /** The IP cell's docket, e.g. "LPU/IDF/2026/0007" — what an inventor
   *  quotes when chasing it. Null on a patent recorded as already filed. */
  reference: string | null;
  /** A two-letter patent-office code (WIPO ST.3), never a country name. */
  jurisdiction: string;
  application_number: string | null;
  publication_number: string | null;
  grant_number: string | null;
  /** Null for everything still inside the university: the office sets it. */
  filing_date: string | null;
  publication_date: string | null;
  grant_date: string | null;
  status: PatentStatus;
  assignee: string | null;
  url: string | null;
  // --- the disclosure, as the IP cell assesses it
  problem_statement: string | null;
  novelty: string | null;
  known_prior_art: string | null;
  /** The field that most often decides whether a patent is possible at all. */
  public_disclosure_date: string | null;
  public_disclosure_note: string | null;
  funding_source: string | null;
  commercial_potential: string | null;
  assessment_note: string | null;
  assessed_by: string | null;
  assessed_by_name: string | null;
  assessed_at: string | null;
  created_by: string;
  creator_name: string;
  verification_status: VerificationStatus;
  verified_by: string | null;
  verified_by_name: string | null;
  verified_at: string | null;
  verification_note: string | null;
  inventors: Inventor[];
  projects: LinkedProject[];
  /** What this record may move to next. The interface offers exactly these,
   *  so it can never show a button the service would refuse. */
  next_statuses: PatentStatus[];
  created_at: string;
}

export interface InventorInput {
  user_id?: string | null;
  external_name?: string | null;
}

export interface PatentInput {
  title: string;
  abstract?: string | null;
  jurisdiction: string;
  application_number?: string | null;
  /**
   * Which way in. False puts the invention to the university and it starts at
   * `disclosed` with no filing date; true records a patent filed elsewhere,
   * which needs one. Not a status field by the back door — it chooses between
   * exactly two entry points, and every move after that goes through the
   * transition table.
   */
  already_filed?: boolean;
  filing_date?: string | null;
  assignee?: string | null;
  url?: string | null;
  problem_statement?: string | null;
  novelty?: string | null;
  known_prior_art?: string | null;
  public_disclosure_date?: string | null;
  public_disclosure_note?: string | null;
  funding_source?: string | null;
  commercial_potential?: string | null;
  inventors: InventorInput[];
  project_ids?: string[];
}

export interface PatentTransition {
  status: PatentStatus;
  on?: string | null;
  number?: string | null;
  /** The IP cell's reasoning. Required to decline. */
  note?: string | null;
}

// --- prior art -------------------------------------------------------------

export interface SimilarPatent {
  id: string;
  title: string;
  jurisdiction: string;
  status: PatentStatus;
  filing_date: string | null;
  grant_number: string | null;
  score: number;
}

export interface RelatedWork {
  title: string;
  venue: string | null;
  year: number | null;
  doi: string | null;
  url: string | null;
  source: string;
}

export interface RegistrySearch {
  name: string;
  description: string;
  url: string;
}

export interface PriorArtResult {
  searched: string;
  similar_patents: SimilarPatent[];
  related_works: RelatedWork[];
  registries: RegistrySearch[];
  /** The literature sources that refused or did not answer, by name. Empty
   *  means every source answered. The screen must name them rather than let
   *  a partial list read as "nothing like this exists" -- which source is
   *  missing tells the reader what the gap covers. */
  /** Absent when the API predates this field -- the browser gets a new bundle
   *  from the CDN minutes before the API finishes rebuilding, so the panel
   *  reads this through a helper that defaults it to empty. */
  unavailable_sources?: string[];
}
