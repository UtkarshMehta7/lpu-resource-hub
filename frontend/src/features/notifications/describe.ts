import type { AppNotification } from "./api";

export interface NotificationLine {
  text: string;
  to: string | null;
  detail?: string;
}

function str(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

/**
 * Turns a notification row into one line of text and a link.
 *
 * Everything comes from the payload captured when the notification was
 * written, so rendering the list needs no extra requests.
 */
export function describeNotification(notification: AppNotification): NotificationLine {
  const payload = notification.payload;
  switch (notification.notification_type) {
    case "application_received":
      return {
        text: `${str(payload, "applicant_name")} applied to “${str(payload, "opportunity_title")}”`,
        to: `/opportunities/${str(payload, "opportunity_id")}/applicants`,
      };
    case "application_decided":
      return {
        text: `Your application to “${str(payload, "opportunity_title")}” is ${str(payload, "status").replace(/_/g, " ")}`,
        to: "/me/applications",
        detail: str(payload, "note") || undefined,
      };
    case "collaboration_request":
      return {
        text: `${str(payload, "sender_name")} sent you a collaboration request`,
        to: "/collaborations",
      };
    case "collaboration_response":
      return {
        text: `${str(payload, "responder_name")} ${str(payload, "status")} your collaboration request`,
        to: "/collaborations?box=sent",
      };
    case "booking_decided":
      return {
        text: `Your booking of ${str(payload, "equipment_name")} was ${str(payload, "status")}`,
        to: "/me/bookings",
        detail: str(payload, "note") || undefined,
      };
    case "project_reviewed":
      return {
        text: `“${str(payload, "project_title")}” was reviewed: now ${str(payload, "status").replace(/_/g, " ")}`,
        to: `/projects/${str(payload, "project_id")}`,
        detail: str(payload, "comment") || undefined,
      };
    case "profile_verified":
      return {
        text: `Your researcher profile is ${str(payload, "status")}`,
        to: "/profile",
        detail: str(payload, "comment") || undefined,
      };
    case "relevant_opportunity": {
      const reasons = payload.reasons;
      return {
        text: `New opportunity that matches you: “${str(payload, "opportunity_title")}”`,
        to: `/opportunities/${str(payload, "opportunity_id")}`,
        detail: Array.isArray(reasons) && typeof reasons[0] === "string" ? reasons[0] : undefined,
      };
    }
    case "deadline_reminder": {
      const days = payload.days_left;
      const kind = str(payload, "kind");
      const base = kind === "funding" ? "/funding" : "/opportunities";
      return {
        text: `“${str(payload, "title")}” closes in ${typeof days === "number" ? days : "a few"} day${days === 1 ? "" : "s"}`,
        to: `${base}/${str(payload, "item_id")}`,
      };
    }
    case "admin_promotion_code":
      // The whole point of the ceremony is that this code is readable here
      // and nowhere else, so it goes in the line itself, not behind a link.
      return {
        text: `${str(payload, "requested_by")} wants to make you an administrator`,
        to: null,
        detail: `Your confirmation code is ${str(payload, "code")}. Read it back to them only if you expect this.`,
      };
    case "message_received":
      return {
        text: `${str(payload, "sender_name")} sent you a message`,
        to: `/messages/${str(payload, "conversation_id")}`,
        detail: str(payload, "preview") || undefined,
      };
    default:
      return { text: "You have a new notification", to: null };
  }
}
