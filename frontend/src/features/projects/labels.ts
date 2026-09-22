export type ProjectStatus = "draft" | "pending_review" | "active" | "completed" | "archived";

export const STATUS_LABEL: Record<ProjectStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  active: "Active",
  completed: "Completed",
  archived: "Archived",
};
