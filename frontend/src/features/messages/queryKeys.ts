/** Query keys shared between the list, the thread and the header link. */
export const CONVERSATIONS_QUERY_KEY = ["conversations"] as const;
export const UNREAD_TOTAL_QUERY_KEY = ["conversations", "unread-total"] as const;

export const threadKey = (conversationId: string) =>
  ["conversation", conversationId, "messages"] as const;
