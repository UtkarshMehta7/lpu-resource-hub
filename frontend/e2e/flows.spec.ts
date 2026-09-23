import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * The four MVP flows from the roadmap, run in order against the seeded demo
 * data: faculty -> coordinator -> student -> admin.
 */

const PASSWORD = process.env.E2E_PASSWORD ?? "demoseedpassword1";
const FACULTY = "DEMOFACULTY01";
// The coordinator whose department scope covers DEMOFACULTY01.
const COORDINATOR = "DEMOCOORDINATOR02";
const STUDENT = "DEMOSTUDENT01";
const ADMIN = "DEMOADMIN";

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

  const page = await (await browser.newContext()).newPage();
  await page.goto("/login");
  await page.getByLabel("Registration number").fill(registrationNumber);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/(dashboard|account|onboarding)/);
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

test("faculty posts an opportunity on the approved project", async ({ browser }) => {
  const page = await sessionFor(browser, FACULTY);
  await page.goto("/opportunities/new");
  await page.getByLabel("Project").selectOption({ label: PROJECT });
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
});

test("student finds the opportunity, applies and tracks the application", async ({ browser }) => {
  const page = await sessionFor(browser, STUDENT);
  await page.goto("/opportunities");
  await page.getByRole("searchbox", { name: "Search" }).fill(OPPORTUNITY);
  await page.getByRole("link", { name: OPPORTUNITY }).click();

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
  await expect(page.getByText("departments")).toBeVisible();

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
  await page.getByLabel("Name").fill(FACILITY);
  await page.getByLabel(/location/i).fill("Block 32");
  await page.getByRole("button", { name: "Create facility" }).click();
  await expect(page.getByRole("heading", { name: FACILITY })).toBeVisible();

  await page.getByRole("link", { name: "Add equipment" }).click();
  await page.getByLabel("Name").fill(EQUIPMENT);
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
  await expect(student.getByText(/coordinator will review it/i)).toBeVisible();

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
  await student.getByRole("button", { name: /☆ Save/ }).click();
  await expect(student.getByRole("button", { name: /★ Saved/ })).toBeVisible();

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
  await student.getByRole("button", { name: "Request collaboration" }).click();
  await student.getByLabel("Message").fill(`Could we collaborate on the ${RUN} field trials?`);
  await student.getByRole("button", { name: "Send request", exact: true }).click();

  // These flows run against the shared dev database, so a request to this
  // researcher may already be pending from an earlier run. Either outcome
  // proves the path works: sent, or refused as a duplicate.
  await expect(
    student
      .getByRole("button", { name: "Request sent" })
      .or(student.getByText(/already have a pending request/i)),
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
  await faculty.getByRole("button", { name: "Create account" }).click();

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
