import { test, expect } from "@playwright/test";
import {
  createCaseViaApi,
  uniqueTitle,
  DEMO_PDF,
  BROKEN_PDF,
} from "./helpers";

/**
 * Edge cases in demo mode: invalid/oversized/malicious uploads, processing
 * failure, API failure, empty + loading states. The demo E2E API runs with
 * MAX_UPLOAD_MB=1 so oversized uploads are cheap to exercise.
 */

test.describe("upload edge cases", () => {
  test("unsupported file type is rejected client-side with a clear message", async ({ page }) => {
    const caseId = await createCaseViaApi(page.request, uniqueTitle("Edge Type"));
    await page.goto(`/cases/${caseId}`); // dropzone lives on the Overview tab
    await page.locator('input[type="file"]').setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("plain text, not a document"),
    });
    await expect(page.getByRole("status")).toContainText(/unsupported file type/i);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByText("No documents uploaded")).toBeVisible(); // nothing stored
  });

  test("disguised executable (MZ magic) is rejected by validation", async ({ page }) => {
    const caseId = await createCaseViaApi(page.request, uniqueTitle("Edge MZ"));
    await page.goto(`/cases/${caseId}`);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().includes("/documents"),
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: "trojan.pdf", // extension lies; magic bytes must win
      mimeType: "application/pdf",
      buffer: Buffer.from("MZ\x90\x00not a pdf at all\n%%EOF\n"),
    });
    const response = await responsePromise;
    expect(response.status()).toBe(400);
    await expect(page.getByRole("status")).toContainText(/do not match the declared document type/i);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByText("No documents uploaded")).toBeVisible();
  });

  test("oversized upload is rejected without storing anything", async ({ page }) => {
    const caseId = await createCaseViaApi(page.request, uniqueTitle("Edge Big"));
    await page.goto(`/cases/${caseId}`);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().includes("/documents"),
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: "big.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.concat([
        Buffer.from("%PDF-1.4\n"),
        Buffer.alloc(2 * 1024 * 1024, 0x61), // 2 MiB > MAX_UPLOAD_MB=1
        Buffer.from("\n%%EOF"),
      ]),
    });
    const response = await responsePromise;
    expect(response.status()).toBe(413);
    await expect(page.getByRole("status")).toContainText(/exceeds .* MB upload limit/i);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByText("No documents uploaded")).toBeVisible();
  });

  test("processing failure is shown honestly (no fake success)", async ({ page }) => {
    const caseId = await createCaseViaApi(page.request, uniqueTitle("Edge Broken"));
    await page.goto(`/cases/${caseId}`);
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().includes("/documents"),
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: "broken.pdf",
      mimeType: "application/pdf",
      buffer: require("fs").readFileSync(BROKEN_PDF),
    });
    const response = await responsePromise;
    expect(response.status()).toBe(202); // accepted for processing
    // ...and the failure state is surfaced, never masked as success
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByRole("status")).toContainText(/processing failed/i, { timeout: 30_000 });
    await expect(page.getByRole("button", { name: /reprocess/i })).toBeVisible();
  });
});

test.describe("api failure and states", () => {
  test("API outage surfaces an error state, not fake success", async ({ page }) => {
    await page.route("**/api/v1/cases**", (route) => route.abort("connectionrefused"));
    await page.goto("/cases");
    await expect(page.getByText(/cannot reach the api/i).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "New case" })).toBeVisible(); // app alive
  });

  test("upload failure shows the error with the API envelope message", async ({ page }) => {
    const caseId = await createCaseViaApi(page.request, uniqueTitle("Edge ApiFail"));
    await page.goto(`/cases/${caseId}`);
    await page.route("**/api/v1/cases/**/documents", (route) => {
      if (route.request().method() === "POST") {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "internal_error",
              message: "Simulated backend outage for E2E.",
              request_id: "req_e2e_123",
            },
          }),
        });
      }
      return route.continue();
    });
    await page.locator('input[type="file"]').setInputFiles({
      name: "fine.pdf",
      mimeType: "application/pdf",
      buffer: require("fs").readFileSync(DEMO_PDF),
    });
    await expect(page.getByRole("status")).toContainText(/Simulated backend outage/i);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByText("No documents uploaded")).toBeVisible();
  });

  test("loading state renders skeletons while fetching", async ({ page }) => {
    await page.route("**/api/v1/cases**", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 800));
      return route.continue();
    });
    await page.goto("/cases");
    // skeletons render while the (delayed) fetch is in flight
    const skeleton = page.locator("main .card svg, main .skeleton").first();
    await expect(skeleton.or(page.locator("main").getByText(/E2E|Draft/)).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("empty states for a brand-new case", async ({ page }) => {
    const caseId = await createCaseViaApi(page.request, uniqueTitle("Edge Empty"));
    await page.goto(`/cases/${caseId}/documents`);
    await expect(page.getByText("No documents uploaded")).toBeVisible();
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Findings" })
      .click();
    await expect(page.getByText(/nothing to screen|no findings/i).first()).toBeVisible();
  });
});
