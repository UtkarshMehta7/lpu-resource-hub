/**
 * Hand-written mirrors of the Pydantic schemas in
 * backend/app/modules/milestones/schemas.py. These have drifted twice in this
 * project's history, so they are written in the same change as the backend.
 */

export type MilestoneStatus = "pending" | "in_progress" | "done" | "cancelled";

/** Derived on every request by the backend, never stored. */
export type Risk = "none" | "on_track" | "at_risk" | "overdue" | "blocked";

export interface MilestoneLink {
  id: string;
  title: string;
  due_date: string;
  status: MilestoneStatus;
}

export interface Milestone {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  due_date: string;
  status: MilestoneStatus;
  position: number;
  completed_at: string | null;
  completed_by: string | null;
  created_at: string;
  updated_at: string;
  risk: Risk;
  /** Negative once the date has passed. */
  days_until_due: number;
  depends_on: MilestoneLink[];
  /** The subset of depends_on actually holding this one up. */
  blocked_by: MilestoneLink[];
}

export interface MyMilestone extends Milestone {
  project_title: string;
}

export interface MilestoneCreate {
  title: string;
  description?: string | null;
  due_date: string;
  position?: number | null;
}

export interface MilestoneUpdate {
  title?: string;
  description?: string | null;
  due_date?: string;
  position?: number | null;
}

export interface AtRiskMilestone extends MilestoneLink {
  risk: Risk;
  days_until_due: number;
}

export interface AtRiskProject {
  project_id: string;
  title: string;
  owner_id: string;
  owner_name: string;
  owner_registration_number: string;
  department_id: string | null;
  overdue_count: number;
  at_risk_count: number;
  blocked_count: number;
  milestones: AtRiskMilestone[];
}
