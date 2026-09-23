import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests for the four MVP flows.
 *
 * They run against the *development* stack (the seeded demo database), not a
 * throwaway one: `playwright.config.ts` starts the Vite dev server and the
 * FastAPI app, and the specs sign in as the demo accounts created by
 * `backend/scripts/seed_demo_data.py`. Set E2E_PASSWORD to that seed
 * password before running:
 *
 *   cd frontend && E2E_PASSWORD=... npx playwright test
 *
 * The flows create their own projects and opportunities (suffixed with a
 * timestamp), so they can be run repeatedly.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // The flows build on each other, so they must not run in parallel.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      // Locally the backend lives in backend/.venv; in CI it is installed
      // into the runner's own Python and `uvicorn` is already on PATH.
      // Putting the venv first covers both without a second config.
      command: 'PATH="$PWD/.venv/bin:$PATH" uvicorn app.main:create_app --factory --port 8000',
      cwd: "../backend",
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
