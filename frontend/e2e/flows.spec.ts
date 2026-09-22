import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * The four MVP flows from the roadmap, run in order against the seeded demo
 * data: faculty -> coordinator -> student -> admin.
 */

const PASSWORD = process.env.E2E_PASSWORD ?? "demoseedpassword1";
const FACULTY = "demo.faculty01@example.com";
// The coordinator whose department scope covers demo.faculty01.
const COORDINATOR = "demo.coordinator02@example.com";
const STUDENT = "demo.student01@example.com";
const ADMIN = "demo.admin@example.com";

const RUN = Date.now().toString().slice(-6);
const PROJECT = `E2E soil sensors ${RUN}`;
const OPPORTUNITY = `E2E field assistant ${RUN}`;

/**
 * One signed-in page per role, reused across the flows below. Logging in
 * again for every test would hit the login rate limiter (5/minute per
 * IP+email, Step 1), and these flows deliberately revisit the same roles.
 */
const sessions = new Map<string, Page>();

async function sessionFor(browser: Browser, email: string): Promise<Page> {
  const existing = sessions.get(email);
  if (existing) return existing;

  const page = await (await browser.newContext()).newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/(dashboard|account|onboarding)/);
  sessions.set(email, page);
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
  await page.getByLabel("Search").fill(OPPORTUNITY);
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
  await page.getByLabel("Search").fill(OPPORTUNITY);
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
