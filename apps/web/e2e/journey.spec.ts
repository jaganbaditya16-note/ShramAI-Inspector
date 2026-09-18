import { test, expect } from "@playwright/test";
import {
  createCaseViaUi,
  openCase,
  expectDocumentStatus,
  DEMO_PDF,
} from "./helpers";

/**
 * The critical customer journey (steps 1-17) in demo mode, desktop viewport.
 * Runs against the isolated demo environment (:3100 web / :8100 API).
 */

test.describe.serial("critical journey", () => {
  let caseTitle: string;

  test("1-3. open app, demo authentication, dashboard loads", async ({ page }) => {
    await page.goto("/");
    // demo mode: the virtual principal is injected, root lands on the dashboard
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    // the shell shows the demo identity (no login required by environment)
    await expect(page.getByText(/Demo Inspector/i).first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  });

  test("4. create a case", async ({ page }) => {
    await page.goto("/cases");
    caseTitle = await createCaseViaUi(page, "E2E Journey");
    await expect(page.getByRole("link", { name: new RegExp(caseTitle) })).toBeVisible();
  });

  test("5. open the case workspace", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    await expect(
      page.getByRole("heading", { name: caseTitle }),
    ).toBeVisible();
    for (const tab of ["Overview", "Findings", "Documents", "Report", "Audit trail"]) {
      await expect(
        page.getByRole("navigation", { name: "Case sections" }).getByRole("link", { name: tab }),
      ).toBeVisible();
    }
  });

  test("6-7. upload a valid PDF and observe processing state", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    // empty state first (Documents tab), then upload from the Overview dropzone
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByText("No documents uploaded")).toBeVisible();
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Overview" })
      .click();
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().includes("/documents"),
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: "journey-payslip.pdf",
      mimeType: "application/pdf",
      buffer: require("fs").readFileSync(DEMO_PDF),
    });
    const response = await responsePromise;
    expect(response.status()).toBe(202); // accepted, never fake success
    // The panel reports completion via the aria-live status region (the
    // transient queued/processing phases are sub-second with the inline
    // pipeline, so the durable completion toast is the reliable observation).
    await expect(page.getByRole("status")).toContainText(/journey-payslip\.pdf processed/i, {
      timeout: 15_000,
    });
    // the document row reaches the processed state without any fixed sleep
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expectDocumentStatus(page, "journey-payslip.pdf", /Processed/i);
    // findings are asserted on the Findings tab in the next journey step
  });

  test("8-9. observe findings and open evidence", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Findings" })
      .click();
    const findingCard = page.locator(".finding-card, article").first();
    await expect(findingCard).toBeVisible();
    // deterministic signal + evidence + review state are distinguished
    await expect(findingCard.getByText(/needs review|needs_review/i)).toBeVisible();
    const evidence = findingCard.getByText(/PAY-001|absent|quote|page/i).first();
    await expect(evidence).toBeVisible();
  });

  test("10-11. review and confirm the finding", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Findings" })
      .click();
    const findingCard = page.locator(".finding-card, article").first();
    await findingCard.getByRole("button", { name: /add note|review note/i }).first().click().catch(
      () => undefined,
    );
    const noteField = findingCard.getByLabel("Review note");
    if (await noteField.isVisible().catch(() => false)) {
      await noteField.fill("Verified against the source document.");
    }
    await findingCard
      .getByRole("button", { name: /^Confirm|Accept/i })
      .first()
      .click();
    await expect(page.getByRole("status")).toContainText(/confirmed/i);
    await expect(findingCard.getByText(/confirmed/i).first()).toBeVisible();
  });

  test("12-13. view score and generate/download the report", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Report" })
      .click();
    await page.getByRole("button", { name: /generate scorecard/i }).click();
    // the scorecard appears with score + risk level (never a fake success);
    // ScoreRing exposes both in its accessible name
    const ring = page.getByRole("img", { name: /screening score \d+ out of 100/i });
    await expect(ring).toBeVisible();
    await expect(ring).toHaveAttribute("aria-label", /risk/i);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /download/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/shramai-scorecard.*\.json$/);
  });

  test("14. view the audit trail", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Audit trail" })
      .click();
    // the audit page renders human-readable action labels
    await expect(page.getByText(/^Document Uploaded/).first()).toBeVisible();
    await expect(page.getByText(/^Document Processed/).first()).toBeVisible();
    // no document contents in the audit trail
    const trail = await page.locator("main").innerText();
    expect(trail).not.toMatch(/SYNTHETIC DEMO PAYSLIP/);
  });

  test("15-16. refresh keeps state; sections navigate", async ({ page }) => {
    await page.goto("/cases");
    await openCase(page, caseTitle);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expectDocumentStatus(page, "journey-payslip.pdf", /Processed/i);
    await page.reload();
    await expectDocumentStatus(page, "journey-payslip.pdf", /Processed/i);
    const sections: Array<[string, RegExp]> = [
      ["Findings", /\/findings$/],
      ["Report", /\/report$/],
      ["Audit trail", /\/audit$/],
      ["Overview", /\/cases\/[0-9a-f-]+$/],
    ];
    for (const [tab, pattern] of sections) {
      await page
        .getByRole("navigation", { name: "Case sections" })
        .getByRole("link", { name: tab })
        .click();
      await expect(page).toHaveURL(pattern);
      await expect(page.getByRole("navigation", { name: "Case sections" }).getByRole("link", { name: tab })).toHaveAttribute(
        "aria-current",
        "page",
      );
    }
  });

  test("17. logout returns to the login page", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByRole("button", { name: /log ?out|sign out/i }).click();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
  });
});
