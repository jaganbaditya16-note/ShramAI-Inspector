import { test, expect } from "@playwright/test";
import { createCaseViaUi } from "./helpers";

/**
 * Required-auth environment (:3200 web / :8101 API): login flows, session
 * handling, unauthorised routes, and the fail-closed malware-scan upload
 * (the auth API enforces scanning with an unreachable clamd host).
 */

const ADMIN_EMAIL = "admin@e2e.example.com";
const ADMIN_PASSWORD = "e2e-admin-password-1";

test.describe("authentication", () => {
  test("unauthenticated user is redirected to login", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
  });

  test("invalid login shows a uniform error without enumeration hints", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill("admin@e2e.example.com");
    await page.getByLabel("Password").fill("wrong-password-9");
    await page.getByRole("button", { name: "Sign in" }).click();
    const alert = page.getByRole("status").or(page.locator(".inline-error, [role=alert]")).first();
    await expect(alert).toBeVisible();
    const message = await alert.innerText();
    expect(message).toMatch(/invalid|incorrect|wrong/i);
    expect(message).not.toMatch(/no such user|unknown user|does not exist/i);
    await expect(page).toHaveURL(/\/login/);
  });

  test("valid login reaches the dashboard; logout ends the session", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(ADMIN_EMAIL);
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByText("E2E Admin").first()).toBeVisible();

    await page.getByRole("button", { name: /log ?out|sign out/i }).click();
    await expect(page).toHaveURL(/\/login/);

    // the revoked session cannot be reused: protected route bounces to login
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("unauthorised route access after logout is refused again", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(ADMIN_EMAIL);
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);
    await page.context().clearCookies();
    await page.goto("/cases");
    await expect(page).toHaveURL(/\/login/);
  });

  test("fail-closed malware scan blocks the upload with a visible error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(ADMIN_EMAIL);
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard/);
    await page.goto("/cases"); // the create-case dialog lives on the cases page

    const caseTitle = await createCaseViaUi(page, "E2E ScanFail");
    await page.getByRole("link", { name: new RegExp(caseTitle) }).first().click();
    // dropzone is on the Overview tab
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().includes("/documents"),
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: "scanned.pdf",
      mimeType: "application/pdf",
      buffer: require("fs").readFileSync(require("path").join(__dirname, "assets", "demo-payslip.pdf")),
    });
    const response = await responsePromise;
    expect(response.status()).toBe(503); // fail-closed: scanner unreachable
    await expect(page.getByRole("status")).toContainText(/unavailable|scanning|try again/i);
    await page
      .getByRole("navigation", { name: "Case sections" })
      .getByRole("link", { name: "Documents" })
      .click();
    await expect(page.getByText("No documents uploaded")).toBeVisible(); // nothing persisted
  });
});
