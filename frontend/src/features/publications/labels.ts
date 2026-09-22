export type PublicationType =
  | "journal_article"
  | "conference_paper"
  | "book_chapter"
  | "book"
  | "preprint"
  | "thesis"
  | "other";

export const PUB_TYPE_LABEL: Record<PublicationType, string> = {
  journal_article: "Journal article",
  conference_paper: "Conference paper",
  book_chapter: "Book chapter",
  book: "Book",
  preprint: "Preprint",
  thesis: "Thesis",
  other: "Other",
};
