import { test, expect } from "@playwright/test";
import { createCaseViaUi, uniqueTitle, DEMO_PDF } from "./helpers";

/**
 * Mobile-viewport smoke: the core journey must work at 390x844.
 * This is the ONLY spec the demo-mobile project runs.
 */

test.use({ viewport: { width: 390, height: 844 } });

test("mobile: dashboard and navigation render", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
});

test("mobile: create case and process a document end to end", async ({ page }) => {
  await page.goto("/cases");
  const title = await createCaseViaUi(page, uniqueTitle("Mobile"));
  await page.getByRole("link", { name: new RegExp(title) }).first().click();
  await expect(page.getByRole("navigation", { name: "Case sections" })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({ // dropzone on Overview
    name: "mobile-payslip.pdf",
    mimeType: "application/pdf",
    buffer: require("fs").readFileSync(DEMO_PDF),
  });
  await expect(page.getByRole("status")).toContainText(/mobile-payslip\.pdf processed/i, {
    timeout: 30_000,
  });
  await page
    .getByRole("navigation", { name: "Case sections" })
    .getByRole("link", { name: "Documents" })
    .click();
  const row = page.getByRole("cell", { name: "mobile-payslip.pdf" }).locator("..");
  await expect(row).toContainText(/Processed/i, { timeout: 15_000 });
  await page
    .getByRole("navigation", { name: "Case sections" })
    .getByRole("link", { name: "Findings" })
    .click();
  await expect(page.locator(".finding-card, article").first()).toBeVisible();
});
