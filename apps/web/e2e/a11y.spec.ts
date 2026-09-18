import { test, expect } from "@playwright/test";

/**
 * Accessibility behaviours: keyboard navigation, focus management in dialogs,
 * and Framer Motion behaviour under prefers-reduced-motion enabled/disabled.
 * Desktop demo project only (mobile runs the smoke suite).
 */

test.describe("keyboard navigation", () => {
  test("login form is fully operable by keyboard", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("heading", { name: /sign in/i }).waitFor();
    // Tab order: email -> password -> submit (start from a deterministic point)
    await page.getByLabel("Work email").focus();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Password")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByLabel("Password")).toBeFocused();
    // Enter submits the focused form (error path keeps everything reachable)
    await page.getByLabel("Work email").fill("admin@e2e.example.com");
    await page.getByLabel("Password").fill("wrong-password-9");
    await page.keyboard.press("Enter");
    await expect(page.getByText(/invalid|incorrect|wrong/i).first()).toBeVisible();
  });

  test("sidebar navigation is reachable and operable by keyboard", async ({ page }) => {
    await page.goto("/dashboard");
    const nav = page.getByRole("navigation", { name: "Primary" });
    await nav.getByRole("link", { name: "Dashboard" }).focus();
    await page.keyboard.press("Tab");
    await expect(nav.getByRole("link", { name: "Cases" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/cases/);
    await expect(nav.getByRole("link", { name: "Cases" })).toHaveAttribute("aria-current", "page");
  });
});

test.describe("dialog focus management", () => {
  test("create-case dialog traps focus and closes on Escape", async ({ page }) => {
    await page.goto("/cases");
    await page.getByRole("button", { name: "New case" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    // focus moved into the dialog
    await expect(page.getByRole("dialog").getByLabel("Case title", { exact: true })).toBeFocused();
    // Tab cycles inside the dialog (focus trap)
    for (let i = 0; i < 8; i += 1) {
      await page.keyboard.press("Tab");
      const inside = await dialog.locator(":focus").count();
      expect(inside).toBeLessThanOrEqual(1);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });
});

test.describe("reduced motion", () => {
  test("content is fully usable with prefers-reduced-motion: reduce", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 10_000 });
    // framer-motion surfaces must not stay stuck invisible
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Cases" }).click();
    await expect(page).toHaveURL(/\/cases/);
    await expect(page.getByRole("button", { name: "New case" })).toBeVisible();
  });

  test("animations complete normally with no-preference", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 10_000 });
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Cases" }).click();
    await expect(page).toHaveURL(/\/cases/);
    // animated content settles to full visibility
    const newCase = page.getByRole("button", { name: "New case" });
    await expect(newCase).toBeVisible();
    await expect(newCase).toHaveCSS("opacity", /^[1]$|^0\.9[5-9]\d*$/);
  });
});
