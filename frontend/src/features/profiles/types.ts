/** Mirrors the backend's profile schemas (app/modules/profiles/schemas.py). */

export type Availability = "available" | "limited" | "unavailable";

export type VerificationStatus = "unverified" | "pending" | "verified" | "rejected";

export interface ProfileLink {
  label: string;
  url: string;
}

export interface StudentProfile {
  profile_type: "student";
  department_id: string | null;
  department_locked: boolean;
  program: string;
  year: number;
  bio: string | null;
  interests: string | null;
  is_discoverable: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResearcherProfile {
  profile_type: "researcher";
  department_id: string | null;
  department_locked: boolean;
  designation: string;
  bio: string | null;
  availability: Availability;
  links: ProfileLink[] | null;
  verification_status: VerificationStatus;
  verified_by: string | null;
  verified_at: string | null;
  /** Set once a profile import has resolved and claimed an ORCID iD. */
  orcid_id: string | null;
  orcid_last_imported_at: string | null;
  created_at: string;
  updated_at: string;
}

export type Profile = StudentProfile | ResearcherProfile;

export interface StudentProfileUpdate {
  program: string;
  department_id?: string | null;
  year: number;
  bio?: string | null;
  interests?: string | null;
  is_discoverable: boolean;
}

export interface ResearcherProfileUpdate {
  designation: string;
  department_id?: string | null;
  bio?: string | null;
  availability: Availability;
  links?: ProfileLink[] | null;
}

export interface SkillEntry {
  skill_id: string;
  proficiency: number;
}

export interface ResearchAreaEntry {
  research_area_id: string;
  is_expertise: boolean;
}

/* ---------------------------------------------------------------- import */

export type ImportWorkStatus =
  "new" | "already_in_register" | "possible_duplicate" | "not_importable";

export interface ImportWorkCandidate {
  key: string;
  title: string;
  doi: string | null;
  venue: string | null;
  year: number | null;
  pub_type: string;
  abstract: string | null;
  /** Where to read the work itself, when it has no DOI. */
  url: string | null;
  authors: string[];
  sources: string[];
  status: ImportWorkStatus;
  matched_publication_id: string | null;
  matched_title: string | null;
  similarity: number | null;
  reason: string | null;
  importable: boolean;
}

export interface ImportFieldSuggestion {
  field: string;
  current: string | null;
  incoming: string | null;
  changed: boolean;
}

export interface ImportPreview {
  orcid: string | null;
  sources_used: string[];
  source_errors: Record<string, string>;
  source_urls: Record<string, string>;
  full_name: string | null;
  affiliation: string | null;
  metrics: Record<string, number>;
  fields: ImportFieldSuggestion[];
  topics: string[];
  works: ImportWorkCandidate[];
  new_count: number;
  known_count: number;
}

export interface AuthorCandidate {
  source: string;
  source_id: string;
  /** Links to the record itself, so a choice can be checked rather than guessed. */
  source_url: string | null;
  full_name: string;
  affiliation: string | null;
  other_affiliations: string[];
  orcid: string | null;
  works_count: number | null;
  cited_by_count: number | null;
  h_index: number | null;
  topics: string[];
}

export interface ImportResult {
  import_id: string;
  applied_fields: string[];
  works_imported: number;
  works_skipped: number;
  works_failed: number;
  source_errors: Record<string, string>;
  /** True when the import sent an already-verified profile back for review. */
  verification_reset: boolean;
}

export interface ImportLookup {
  orcid?: string | null;
  name?: string | null;
  affiliation?: string | null;
  /** `source_id` of a candidate the researcher picked. Wins over the name. */
  openalex_author_id?: string | null;
}

export interface ImportHistoryEntry {
  id: string;
  orcid_id: string | null;
  works_found: number;
  works_imported: number;
  works_already_known: number;
  applied_fields: string[];
  created_at: string;
}
