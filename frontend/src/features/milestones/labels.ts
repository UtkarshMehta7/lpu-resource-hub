import type { PillTone } from "@/components/ui/StatusPill";

import type { MilestoneStatus, Risk } from "./types";

/**
 * How a milestone's state is said and coloured, in one place.
 *
 * Colour alone is never the signal -- every pill carries a word too, because
 * a timeline read only by hue is unreadable to a good number of people.
 */

export const STATUS_LABELS: Record<MilestoneStatus, string> = {
  pending: "Not started",
  in_progress: "In progress",
  done: "Done",
  cancelled: "Cancelled",
};

export const RISK_LABELS: Record<Risk, string> = {
  none: "Settled",
  on_track: "On track",
  at_risk: "Due soon",
  overdue: "Overdue",
  blocked: "Blocked",
};

export const RISK_TONES: Record<Risk, PillTone> = {
  none: "neutral",
  on_track: "positive",
  at_risk: "warning",
  overdue: "negative",
  blocked: "warning",
};

/** Bar fills for the timeline. Kept beside the pill tones so they agree. */
export const RISK_COLOURS: Record<Risk, string> = {
  none: "#9aa3ad",
  on_track: "#2f855a",
  at_risk: "#b7791f",
  overdue: "#c53030",
  blocked: "#7a5bb0",
};

export function describeDue(daysUntilDue: number): string {
  if (daysUntilDue === 0) return "due today";
  if (daysUntilDue === 1) return "due tomorrow";
  if (daysUntilDue === -1) return "1 day late";
  if (daysUntilDue < 0) return `${Math.abs(daysUntilDue)} days late`;
  return `in ${daysUntilDue} days`;
}

export function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
