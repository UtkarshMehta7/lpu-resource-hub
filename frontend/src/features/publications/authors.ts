import type { AuthorInput } from "./api";

export interface AuthorRow {
  key: string;
  kind: "user" | "external";
  userId: string | null;
  name: string;
}

let nextKey = 0;
export function newAuthorRow(
  kind: AuthorRow["kind"],
  userId: string | null = null,
  name = "",
): AuthorRow {
  nextKey += 1;
  return { key: `author-${nextKey}`, kind, userId, name };
}

/** Returns the API author list, or an error message if a row is incomplete. */
export function toAuthorInputs(rows: AuthorRow[]): AuthorInput[] | string {
  if (rows.length === 0) return "Add at least one author.";
  const inputs: AuthorInput[] = [];
  for (const row of rows) {
    if (row.kind === "user") {
      if (!row.userId) return "Pick a researcher for every platform author, or remove the row.";
      inputs.push({ user_id: row.userId });
    } else {
      const name = row.name.trim();
      if (!name) return "Every external author needs a name.";
      inputs.push({ external_name: name });
    }
  }
  return inputs;
}
