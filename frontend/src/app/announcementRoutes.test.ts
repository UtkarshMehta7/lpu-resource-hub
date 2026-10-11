import { matchRoutes } from "react-router-dom";
import { describe, expect, it } from "vitest";

/**
 * `/announcements/new` must not be swallowed by `/announcements/:id`.
 *
 * This is the frontend's version of the trap documented for
 * `/publications/duplicates`, which FastAPI matched in registration order and
 * parsed "duplicates" as a UUID. React Router ranks by specificity instead,
 * so a static segment should win — but here the two routes sit in DIFFERENT
 * branches of the tree, because the dynamic one is open to every role while
 * the static ones are behind a RoleRoute. That is unusual enough to pin:
 * without it, "new" would be fetched as an announcement id and every poster
 * would see "Announcement not found" instead of the form.
 */
const ROUTES = [
  { path: "announcements", element: "board" },
  { path: "announcements/:announcementId", element: "detail" },
  {
    element: "RoleRoute",
    children: [
      { path: "announcements/mine", element: "mine" },
      { path: "announcements/new", element: "form" },
      { path: "announcements/:announcementId/edit", element: "edit" },
    ],
  },
];

function leafFor(path: string): unknown {
  const matches = matchRoutes(ROUTES, path);
  return matches?.[matches.length - 1]?.route.element;
}

describe("announcement route ranking", () => {
  it.each([
    ["/announcements", "board"],
    ["/announcements/new", "form"],
    ["/announcements/mine", "mine"],
    ["/announcements/8f14e45f-ea8d-4b2e-9a7e-0c1d2e3f4a5b", "detail"],
    ["/announcements/8f14e45f-ea8d-4b2e-9a7e-0c1d2e3f4a5b/edit", "edit"],
  ])("sends %s to the %s route", (path, expected) => {
    expect(leafFor(path)).toBe(expected);
  });
});
