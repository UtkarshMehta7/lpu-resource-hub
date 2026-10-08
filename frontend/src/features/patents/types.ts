/**
 * Hand-written mirrors of the backend's Pydantic schemas.
 *
 * These have drifted twice before, so they are written in the same change as
 * the schemas they mirror -- see backend/app/modules/patents/schemas.py.
 */

export type PatentStatus = "filed" | "published" | "granted" | "lapsed" | "rejected" | "withdrawn";

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
  /** A two-letter patent-office code (WIPO ST.3), never a country name. */
  jurisdiction: string;
  application_number: string | null;
  publication_number: string | null;
  grant_number: string | null;
  filing_date: string;
  publication_date: string | null;
  grant_date: string | null;
  status: PatentStatus;
  assignee: string | null;
  url: string | null;
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
  filing_date: string;
  assignee?: string | null;
  url?: string | null;
  inventors: InventorInput[];
  project_ids?: string[];
}

export interface PatentTransition {
  status: PatentStatus;
  on?: string | null;
  number?: string | null;
}

// --- prior art -------------------------------------------------------------

export interface SimilarPatent {
  id: string;
  title: string;
  jurisdiction: string;
  status: PatentStatus;
  filing_date: string;
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
  /** True when an index could not be reached: the list is partial and the
   *  screen must say so rather than read as "nothing like this exists". */
  literature_unavailable: boolean;
}
