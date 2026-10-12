import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * The four MVP flows from the roadmap, run in order against the seeded demo
 * data: faculty -> coordinator -> student -> admin.
 */

const PASSWORD = process.env.E2E_PASSWORD ?? "demoseedpassword1";
const FACULTY = "12500201";
// The coordinator whose department scope covers the faculty above.
const COORDINATOR = "12500102";
const STUDENT = "12500301";
const ADMIN = "12500001";

const RUN = Date.now().toString().slice(-6);
const PROJECT = `E2E soil sensors ${RUN}`;
const OPPORTUNITY = `E2E field assistant ${RUN}`;
const FACILITY = `E2E soil lab ${RUN}`;
const EQUIPMENT = `E2E moisture probe ${RUN}`;
const FUNDING = `E2E demo seed grant ${RUN}`;

/**
 * One signed-in page per role, reused across the flows below. Logging in
 * again for every test would hit the login rate limiter (5/minute per
 * IP + registration number, Step 1), and these flows revisit the same roles.
 */
const sessions = new Map<string, Page>();

async function sessionFor(browser: Browser, registrationNumber: string): Promise<Page> {
  const existing = sessions.get(registrationNumber);
  if (existing) return existing;

  // The two entrances are separate and the server enforces it (ADR 0020):
  // an administrator is refused at /login, everyone else at /admin/login.
  // Signing every role in at /login is what broke this suite when the
  // portals landed.
  const isAdmin = registrationNumber === ADMIN;
  const page = await (await browser.newContext()).newPage();
  await page.goto(isAdmin ? "/admin/login" : "/login");
  await page.getByLabel("Registration number").fill(registrationNumber);
  await page.getByLabel("Password").fill(PASSWORD);
  await page
    .getByRole("button", { name: isAdmin ? "Sign in to administration" : "Log in" })
    .click();
  // Anchored: /\/admin/ alone also matches /admin/login, so a *failed*
  // sign-in would satisfy it and the test would fail later, somewhere
  // confusing.
  await expect(page).toHaveURL(isAdmin ? /\/admin$/ : /\/(dashboard|account|onboarding)/);
  sessions.set(registrationNumber, page);
  return page;
}

test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  for (const page of sessions.values()) {
    await page.context().close();
  }
  sessions.clear();
});

test("faculty creates a project and submits it for review", async ({ browser }) => {
  const page = await sessionFor(browser, FACULTY);
  await page.goto("/projects/new");
  await page.getByLabel("Title").fill(PROJECT);
  await page.getByLabel("Summary").fill("Low-cost soil moisture sensors for smallholder farms.");
  await page
    .getByLabel("Description")
    .fill("We design, build and field-test low-cost soil moisture sensors with local farmers.");
  await page.getByRole("button", { name: "Create draft" }).click();

  await expect(page.getByRole("heading", { name: PROJECT })).toBeVisible();
  await page.getByRole("button", { name: "Submit" }).click();
  await page.getByRole("button", { name: "Submit" }).last().click();
  await expect(page.getByText("Pending review")).toBeVisible();
});

test("coordinator reviews the project and approves it", async ({ browser }) => {
  const page = await sessionFor(browser, COORDINATOR);
  await page.goto("/coordinator/review-queue");
  const row = page.locator("li", { hasText: PROJECT });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("button", { name: "Approve" }).last().click();
  await expect(page.locator("li", { hasText: PROJECT })).toHaveCount(0);
});

test("faculty adds a colleague to the team directly", async ({ browser }) => {
  // The other way onto a team. Accepting an application is how a stranger
  // joins; this is how the lead adds somebody they already work with, and
  // POST /projects/{id}/members had been built and left uncalled since
  // projects shipped.
  const page = await sessionFor(browser, FACULTY);
  await page.goto("/projects/mine");
  await page.getByRole("link", { name: PROJECT }).click();

  const team = page.locator("section").filter({ has: page.getByRole("heading", { name: "Team" }) });
  await team.getByRole("button", { name: "Add someone to the team" }).click();

  // A researcher rather than a student: students carry a discoverability
  // opt-in (`is_discoverable`), so which of them this search can see depends
  // on the seed, and an assertion must not.
  await page.getByLabel("Role on this project").fill("Co-investigator");
  await page.getByLabel("Find a person").fill("12500202");
  await team.getByRole("button", { name: "Add" }).click();

  await expect(team.getByText("Co-investigator")).toBeVisible();
});

test("faculty posts an opening from the project's own hiring section", async ({ browser }) => {
  const page = await sessionFor(browser, FACULTY);
  await page.goto("/projects/mine");
  await page.getByRole("link", { name: PROJECT }).click();

  // The section is "Hiring" for the lead and "Open positions" for everybody
  // else, because the lead's list holds drafts and closed openings too.
  const hiring = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Hiring" }) });
  await expect(hiring).toBeVisible();
  await hiring.getByRole("link", { name: "Post an opening" }).click();

  // The link carries ?project_id=, so the form arrives knowing which project
  // it is hiring for. Without it the lead has to find their own project again
  // in a dropdown, and the wrong choice files the opening against the wrong
  // team. jsdom cannot catch this: the value comes from the URL.
  await expect(page.getByLabel("Project")).not.toHaveValue("");
  await page.getByLabel("Title").fill(OPPORTUNITY);
  await page.getByLabel("Positions").fill("1");
  const deadline = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  await page.getByLabel("Deadline").fill(deadline);
  await page
    .getByLabel("Description")
    .fill("Help calibrate soil moisture sensors during weekly field trials.");
  await page.getByRole("button", { name: "Create draft" }).click();

  await expect(page.getByRole("heading", { name: OPPORTUNITY })).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await page.getByRole("button", { name: "Publish" }).last().click();
  await expect(page.getByText("Open", { exact: false }).first()).toBeVisible();

  // Back on the project, the lead can see it and that nobody has applied --
  // the two things the project page could not previously tell them.
  await page.goto("/projects/mine");
  await page.getByRole("link", { name: PROJECT }).click();
  const posted = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Hiring" }) });
  await expect(posted.getByRole("link", { name: OPPORTUNITY })).toBeVisible();
  await expect(posted.getByText("No applications yet.")).toBeVisible();
});

test("the opening reaches the department's notice board by itself", async ({ browser }) => {
  // ADR 0041. demo.faculty01 and demo.student01 are always in the same
  // department -- both seed loops index from 1 over the same list -- so the
  // department-scoped notice is one this student is addressed by.
  const page = await sessionFor(browser, STUDENT);
  await page.goto("/announcements");
  await page.getByRole("searchbox", { name: "Search" }).fill(OPPORTUNITY);

  const notice = page.getByRole("link", { name: new RegExp(`Opening: ${OPPORTUNITY}`) });
  await expect(notice).toBeVisible();
  await notice.click();

  // The notice carries the way to the thing it is about, rather than leaving
  // the reader to find it on the board by name.
  await page.getByRole("link", { name: "Open the position" }).click();
  await expect(page.getByRole("heading", { name: OPPORTUNITY })).toBeVisible();
});

test("student finds the opportunity, applies and tracks the application", async ({ browser }) => {
  const page = await sessionFor(browser, STUDENT);
  // From the PROJECT, which is where somebody reading about the work asks
  // whether they can join it. The board still works; this is the route that
  // did not exist.
  await page.goto("/projects");
  await page.getByRole("searchbox", { name: "Search" }).fill(PROJECT);
  await page.getByRole("link", { name: PROJECT }).first().click();
  const openings = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Open positions" }) });
  await expect(openings).toBeVisible();
  await openings.getByRole("link", { name: OPPORTUNITY }).click();

  await page.getByLabel(/good fit/i).fill("I have built and calibrated soil sensors before.");
  await page.getByRole("button", { name: "Submit application" }).click();
  await expect(page.getByText(/you've applied/i)).toBeVisible();

  await page.goto("/me/applications");
  const application = page.locator("li", { hasText: OPPORTUNITY });
  await expect(application).toBeVisible();
  await expect(application.getByText("Submitted").first()).toBeVisible();

  // ...and it shows up on the dashboard as an upcoming deadline.
  await page.goto("/dashboard");
  await expect(page.getByText(OPPORTUNITY).first()).toBeVisible();
});

test("faculty reviews the applicant and accepts them", async ({ browser }) => {
  const page = await sessionFor(browser, FACULTY);
  await page.goto("/opportunities");
  await page.getByRole("searchbox", { name: "Search" }).fill(OPPORTUNITY);
  await page.getByRole("link", { name: OPPORTUNITY }).click();
  await page.getByRole("link", { name: "Review applicants" }).click();

  await page.getByRole("button", { name: "View" }).first().click();
  const drawer = page.getByRole("complementary", { name: "Application details" });
  await drawer.getByRole("button", { name: "Mark under review" }).click();
  await drawer.getByRole("button", { name: "Accept" }).click();
  await expect(drawer.getByText("Accepted")).toBeVisible();
});

test("admin changes a role and sees platform stats", async ({ browser }) => {
  const page = await sessionFor(browser, ADMIN);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Platform" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
  // Scoped to the Platform section and exact, because the word is no longer
  // unique on this page: the dashboard now carries the announcements section
  // (ADR 0038), and a seeded notice reads "...departments to confirm their
  // figures by Friday". A bare getByText matched both and Playwright's
  // strict mode rightly refused to choose -- the same loose-matcher trap
  // AGENTS.md records against getByLabel.
  const platform = page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Platform" }) });
  await expect(platform.getByText("departments", { exact: true })).toBeVisible();

  await page.goto("/admin/users");
  // The admin's own row is disabled, so take the first row they may change
  // and pin the locator to that person: the table refetches after a change.
  const firstEditable = page.locator('select[aria-label^="Role for"]:not([disabled])').first();
  await expect(firstEditable).toBeVisible();
  const label = await firstEditable.getAttribute("aria-label");
  expect(label).not.toBeNull();
  const roleSelect = page.getByLabel(label as string);

  const original = await roleSelect.inputValue();
  const next = original === "student" ? "faculty" : "student";

  await roleSelect.selectOption(next);
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(roleSelect).toHaveValue(next);

  // Put the demo data back the way it was seeded.
  await roleSelect.selectOption(original);
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(roleSelect).toHaveValue(original);
});

test("coordinator lists a facility and its equipment", async ({ browser }) => {
  const page = await sessionFor(browser, COORDINATOR);
  await page.goto("/facilities/new");
  await page.getByLabel("Name", { exact: true }).fill(FACILITY);
  await page.getByLabel(/location/i).fill("Block 32");
  await page.getByRole("button", { name: "Create facility" }).click();
  await expect(page.getByRole("heading", { name: FACILITY })).toBeVisible();

  await page.getByRole("link", { name: "Add equipment" }).click();
  await page.getByLabel("Name", { exact: true }).fill(EQUIPMENT);
  await page.getByLabel(/longest booking/i).fill("4");
  await page.getByRole("button", { name: "Add equipment" }).click();
  await expect(page.getByRole("heading", { name: EQUIPMENT })).toBeVisible();
  await expect(page.getByText(/needs approval/i)).toBeVisible();
});

test("student requests a slot and the coordinator approves it", async ({ browser }) => {
  const student = await sessionFor(browser, STUDENT);
  await student.goto("/facilities");
  await student.getByRole("searchbox", { name: "Search" }).fill(FACILITY);
  await student.getByRole("link", { name: FACILITY }).click();
  await student.getByRole("link", { name: EQUIPMENT }).click();

  // Pick a free hour from next week's calendar, so "now" can't interfere.
  await student.getByRole("button", { name: "Next →" }).click();
  await student
    .getByRole("button", { name: /^Book / })
    .first()
    .click();
  await student.getByLabel(/what do you need it for/i).fill("Calibrating probes for field trials.");
  await student.getByRole("button", { name: "Request this slot" }).click();
  // Named by the room, not by a role: a booking goes to the facility's
  // custodian when it has one and to the department's coordinator when it
  // does not, so the confirmation can no longer name either. This facility
  // has no custodian, and the coordinator approves it below.
  await expect(
    student.getByText(new RegExp(`whoever looks after ${FACILITY} will review it`, "i")),
  ).toBeVisible();

  const coordinator = await sessionFor(browser, COORDINATOR);
  await coordinator.goto("/coordinator/booking-queue");
  const request = coordinator.locator("li", { hasText: EQUIPMENT });
  await expect(request).toBeVisible();
  await request.getByRole("button", { name: "Approve" }).click();
  await expect(coordinator.locator("li", { hasText: EQUIPMENT })).toHaveCount(0);

  await student.goto("/me/bookings");
  const booking = student.locator("li", { hasText: EQUIPMENT });
  await expect(booking).toBeVisible();
  await expect(booking.getByText("Approved")).toBeVisible();
});

test("an approved booking blocks the slot in the calendar", async ({ browser }) => {
  // The database guarantee (two approvals can never overlap) is proven in
  // backend/tests/test_bookings.py, including concurrently. What matters
  // here is that people can see the slot is gone.
  const faculty = await sessionFor(browser, FACULTY);
  await faculty.goto("/facilities");
  await faculty.getByRole("searchbox", { name: "Search" }).fill(FACILITY);
  await faculty.getByRole("link", { name: FACILITY }).click();
  await faculty.getByRole("link", { name: EQUIPMENT }).click();
  await faculty.getByRole("button", { name: "Next →" }).click();

  // The student's approved hour shows as taken, and isn't offered again.
  await expect(faculty.getByText("Booked").first()).toBeVisible();

  const student = await sessionFor(browser, STUDENT);
  await student.goto("/me/bookings");
  const booking = student.locator("li", { hasText: EQUIPMENT }).first();
  await expect(booking.getByText("Approved")).toBeVisible();
});

test("coordinator lists a funding call and a student saves it", async ({ browser }) => {
  const coordinator = await sessionFor(browser, COORDINATOR);
  await coordinator.goto("/funding/new");
  await coordinator.getByLabel("Title").fill(FUNDING);
  await coordinator.getByLabel("Organisation").fill("Demo Research Council");
  const deadline = new Date(Date.now() + 21 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  await coordinator.getByLabel("Deadline").fill(deadline);
  await coordinator
    .getByLabel("Description")
    .fill("A fictional demo call used by the end-to-end tests.");
  await coordinator.getByRole("button", { name: "Add call" }).click();
  await expect(coordinator.getByRole("heading", { name: FUNDING })).toBeVisible();

  const student = await sessionFor(browser, STUDENT);
  await student.goto("/funding");
  await student.getByRole("searchbox", { name: "Search" }).fill(FUNDING);
  await student.getByRole("link", { name: FUNDING }).click();
  // exact: true because "Save" is a prefix of "Saved". The star is an SVG
  // now, not a ☆/★ character, so it contributes nothing to the accessible
  // name -- which is the point of the icon, and what broke this assertion.
  await student.getByRole("button", { name: "Save", exact: true }).click();
  await expect(student.getByRole("button", { name: "Saved", exact: true })).toBeVisible();

  // It shows up in Saved and as an upcoming deadline on the dashboard.
  await student.goto("/me/saved?type=funding");
  await expect(student.getByRole("link", { name: FUNDING })).toBeVisible();
  await student.goto("/dashboard");
  await expect(student.getByText(FUNDING)).toBeVisible();
});

test("a collaboration request shows up in the recipient's notifications", async ({ browser }) => {
  const student = await sessionFor(browser, STUDENT);
  await student.goto("/researchers");
  await student
    .getByRole("link", { name: /Demo Faculty 0/ })
    .first()
    .click();
  // The control reflects the relationship, so it renders one of four things.
  // Wait for whichever it is BEFORE counting: count() does not auto-wait, so
  // asking too early returns 0 and the branch below reads "already
  // collaborating" from a page that simply had not finished loading.
  const offer = student.getByRole("button", { name: /Request collaboration|Collaborate again/ });
  const settled = student
    .getByRole("link", { name: /open conversation/i })
    .or(student.getByText(/request pending/i))
    .or(student.getByRole("button", { name: "Accept" }));
  await expect(offer.or(settled).first()).toBeVisible();

  if ((await offer.count()) === 0) {
    // Nothing to request: they already have a live relationship, or one is
    // waiting on an answer. Either is a pass -- it is the state the interface
    // is supposed to show instead of offering to start it again (ADR 0023).
    await expect(settled.first()).toBeVisible();
    return;
  }
  await offer.first().click();
  // exact: true, because the header's Messages link is labelled "Messages"
  // and getByLabel substring-matches by default.
  await student
    .getByLabel("Message", { exact: true })
    .fill(`Could we collaborate on the ${RUN} field trials?`);
  await student.getByRole("button", { name: "Send request", exact: true }).click();

  // These flows run against the shared development database, so the pair may
  // already have a live relationship from an earlier run. Every one of these
  // outcomes proves the path works: the request went, it is pending, or the
  // server refused it because they already collaborate (ADR 0023).
  await expect(
    student
      .getByText(/request pending/i)
      .or(student.getByRole("link", { name: /open conversation/i }))
      .or(student.getByText(/already have a collaboration/i)),
  ).toBeVisible();

  // Either way the recipient has the notification.
  const faculty = await sessionFor(browser, FACULTY);
  await faculty.goto("/me/notifications");
  await expect(faculty.getByText(/sent you a collaboration request/i).first()).toBeVisible();
});

test("smart search answers a question in plain language", async ({ browser }) => {
  const student = await sessionFor(browser, STUDENT);
  await student.goto("/search");
  await expect(student.getByText("Try a question")).toBeVisible();

  await student.getByLabel(/what are you looking for/i).fill("soil moisture sensors for farms");
  await student.getByRole("button", { name: "Search", exact: true }).click();
  await expect(student.getByText(/match(es)? for/)).toBeVisible();

  // The keyword toggle switches mode and re-runs the same query.
  await student.getByRole("button", { name: "Keyword" }).click();
  await expect(student.getByText(/matches the exact words/i)).toBeVisible();
  await expect(student).toHaveURL(/mode=keyword/);
});

test("faculty adds a student, who must set their own password first", async ({ browser }) => {
  const faculty = await sessionFor(browser, FACULTY);
  await faculty.goto("/people/new");
  const registrationNumber = `E2E${RUN}`;
  await faculty.getByLabel("Registration number").fill(registrationNumber);
  await faculty.getByLabel("Full name").fill(`E2E Student ${RUN}`);
  // The button names the role being provisioned (ADR 0019).
  await faculty.getByRole("button", { name: "Add student" }).click();

  await expect(faculty.getByText(/account created for/i)).toBeVisible();
  const temporaryPassword = (await faculty.locator("code").first().innerText()).trim();
  expect(temporaryPassword.length).toBeGreaterThan(8);

  // The new student can sign in, but lands on the password screen and can go
  // nowhere else until they choose one.
  const page = await (await browser.newContext()).newPage();
  await page.goto("/login");
  await page.getByLabel("Registration number").fill(registrationNumber);
  await page.getByLabel("Password").fill(temporaryPassword);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/set-password/);

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/set-password/);

  const chosenPassword = `chosen-${RUN}-password`;
  await page.getByLabel("Temporary password").fill(temporaryPassword);
  await page.getByLabel("New password", { exact: true }).fill(chosenPassword);
  await page.getByLabel("Confirm new password").fill(chosenPassword);
  await page.getByRole("button", { name: "Set my password" }).click();

  // Changing it signs every session out, so they sign in with their own.
  await expect(page).toHaveURL(/login/);
  await page.getByLabel("Registration number").fill(registrationNumber);
  await page.getByLabel("Password").fill(chosenPassword);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/dashboard|account/);
  await page.context().close();

  // ...and the faculty member who enrolled them can remove them again, which
  // is also how this run cleans up after itself: E2E runs against the
  // development database, so an account per run would accumulate forever.
  await faculty.goto("/people");
  const row = faculty.locator("tr", { hasText: registrationNumber });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: /^Delete/ }).click();
  // The cascade is stated before it happens (ADR 0021).
  await expect(
    faculty.getByText(/nothing else is deleted with it|Deleted along with/i),
  ).toBeVisible();
  await faculty.getByRole("button", { name: "Delete permanently" }).click();
  await expect(faculty.locator("tr", { hasText: registrationNumber })).toHaveCount(0);
});

test("coordinator reads scoped analytics; admin reads the audit log", async ({ browser }) => {
  const coordinator = await sessionFor(browser, COORDINATOR);
  await coordinator.goto("/analytics");
  await expect(coordinator.getByRole("heading", { name: "Analytics" })).toBeVisible();
  // A coordinator's numbers stop at their department, and the page says so.
  await expect(coordinator.getByText(/for your department only/i)).toBeVisible();
  await expect(coordinator.getByText("Collaboration network")).toBeVisible();

  const admin = await sessionFor(browser, ADMIN);
  await admin.goto("/analytics");
  await expect(admin.getByText(/across the whole platform/i)).toBeVisible();

  await admin.goto("/admin/audit-logs");
  await expect(admin.getByRole("heading", { name: "Audit log" })).toBeVisible();
  await admin.getByLabel("Action").fill("user.role_changed");
  await expect(admin.getByText("user.role_changed").first()).toBeVisible();

  await admin.goto("/admin/settings");
  await expect(admin.getByText(/recommendation weights/i)).toBeVisible();
});

test("no page scrolls sideways on a phone", async ({ browser }) => {
  // The header's mark and its four action icons together needed more than a
  // 360px screen has, so EVERY page scrolled horizontally -- 80px at 360, 50
  // at 390, 26 at 414. Nothing in the component tests could see it: jsdom
  // applies no media queries and measures no layout, so this is the only
  // place the regression can be caught.
  const page = await sessionFor(browser, FACULTY);
  await page.setViewportSize({ width: 360, height: 800 });

  for (const path of ["/dashboard", "/projects", "/opportunities", "/announcements"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path} overflows by ${overflow}px at 360`).toBeLessThanOrEqual(0);
  }

  // The prototype label is the one part of the mark that must survive the
  // narrowest screen: it is what says this is not an official LPU system.
  // Scoped to the header -- the footer carries the same disclaimer, and a
  // bare getByText matches both.
  await expect(page.locator("header").getByText("Prototype")).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
});
