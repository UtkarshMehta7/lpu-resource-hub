import type { PillTone } from "@/components/ui/StatusPill";

/**
 * Mirrors app/modules/deduplication/schemas.py.
 *
 * Hand-written, like every other feature's types here, and they have drifted
 * twice before -- so this file changes in the same commit as the Pydantic
 * schemas, never after.
 */

export type DuplicateStatus = "suspected" | "merged" | "separate" | "ignored";

export interface PublicationSide {
  id: string;
  title: string;
  doi: string | null;
  url: string | null;
  venue: string | null;
  year: number | null;
  pub_type: string;
  authors: string[];
  /** What a merge would carry over, so the cost is visible before deciding. */
  project_count: number;
  created_at: string;
}

export interface DuplicateEvidence {
  title_similarity?: number;
  identical_normalised_title?: boolean;
  same_year?: boolean;
  years?: (number | null)[];
  shared_doi?: boolean;
  doi_on_one_side_only?: boolean;
  same_venue?: boolean;
  shared_authors?: string[];
  shared_author_count?: number;
}

export interface DuplicateReview {
  id: string;
  status: DuplicateStatus;
  score: number;
  evidence: DuplicateEvidence;
  /** Null once a merge has removed one side, or a record was deleted. */
  publication_a: PublicationSide | null;
  publication_b: PublicationSide | null;
  merged_into_id: string | null;
  can_undo: boolean;
  decided_by: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
}

export interface ScanResult {
  examined: number;
  pairs_found: number;
  pairs_new: number;
  pairs_already_decided: number;
}

export type DuplicateAction = "merge" | "separate" | "ignore";

export const STATUS_LABELS: Record<DuplicateStatus, string> = {
  suspected: "Needs review",
  merged: "Merged",
  separate: "Different works",
  ignored: "Set aside",
};

export const STATUS_TONES: Record<DuplicateStatus, PillTone> = {
  suspected: "warning",
  merged: "info",
  separate: "positive",
  ignored: "neutral",
};
