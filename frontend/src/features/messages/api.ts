import type { Role } from "@/features/auth/types";
import { apiClient } from "@/lib/api/client";

/** Mirrors the backend's messages schemas (app/modules/messages/schemas.py). */
export type SubjectKind = "collaboration" | "project";

export interface Participant {
  user_id: string;
  full_name: string;
  registration_number: string;
  role: Role;
}

export interface Conversation {
  id: string;
  subject_kind: SubjectKind;
  subject_id: string;
  title: string;
  participants: Participant[];
  /** False once the collaboration behind it has ended: readable, not writable. */
  open: boolean;
  unread_count: number;
  last_message_at: string | null;
  preview: string | null;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_name: string;
  sender_registration_number: string;
  /** null when a moderator has hidden it; the message keeps its place. */
  body: string | null;
  hidden: boolean;
  created_at: string;
}

export interface MessagePage {
  items: Message[];
  /** Pass back as `after` to fetch only what has arrived since. */
  next_after: string | null;
}

export async function fetchConversations(): Promise<Conversation[]> {
  const response = await apiClient.get<Conversation[]>("/api/v1/me/conversations");
  return response.data;
}

export async function fetchUnreadTotal(): Promise<number> {
  const response = await apiClient.get<number>("/api/v1/me/conversations/unread-count");
  return response.data;
}

export async function fetchConversation(conversationId: string): Promise<Conversation> {
  const response = await apiClient.get<Conversation>(`/api/v1/conversations/${conversationId}`);
  return response.data;
}

export async function fetchMessages(
  conversationId: string,
  after?: string | null,
): Promise<MessagePage> {
  const response = await apiClient.get<MessagePage>(
    `/api/v1/conversations/${conversationId}/messages`,
    { params: after ? { after } : undefined },
  );
  return response.data;
}

export async function sendMessage(conversationId: string, body: string): Promise<Message> {
  const response = await apiClient.post<Message>(
    `/api/v1/conversations/${conversationId}/messages`,
    { body },
  );
  return response.data;
}

export async function markConversationRead(conversationId: string): Promise<void> {
  await apiClient.post(`/api/v1/conversations/${conversationId}/read`);
}

/** Opens the team thread for a project, or returns the existing one. */
export async function openProjectConversation(projectId: string): Promise<Conversation> {
  const response = await apiClient.post<Conversation>(`/api/v1/projects/${projectId}/conversation`);
  return response.data;
}
