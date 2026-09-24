import { apiClient } from "@/lib/api/client";

export type NotificationType =
  | "application_received"
  | "application_decided"
  | "collaboration_request"
  | "collaboration_response"
  | "booking_decided"
  | "project_reviewed"
  | "profile_verified"
  | "relevant_opportunity"
  | "deadline_reminder"
  | "admin_promotion_code"
  | "message_received";

export interface AppNotification {
  id: string;
  notification_type: NotificationType;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  unread_count: number;
  items: AppNotification[];
}

export async function fetchNotifications(unreadOnly = false): Promise<NotificationList> {
  const response = await apiClient.get<NotificationList>("/api/v1/me/notifications", {
    params: unreadOnly ? { unread_only: true } : undefined,
  });
  return response.data;
}

export async function markNotificationRead(id: string): Promise<AppNotification> {
  const response = await apiClient.post<AppNotification>(`/api/v1/me/notifications/${id}/read`);
  return response.data;
}

export async function markAllNotificationsRead(): Promise<number> {
  const response = await apiClient.post<{ marked_read: number }>(
    "/api/v1/me/notifications/read-all",
  );
  return response.data.marked_read;
}
