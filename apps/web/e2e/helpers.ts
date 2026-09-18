import { expect, type Page, type APIRequestContext } from "@playwright/test";
import path from "path";

export const ASSETS = path.join(__dirname, "assets");
export const DEMO_PDF = path.join(ASSETS, "demo-payslip.pdf");
export const BROKEN_PDF = path.join(ASSETS, "broken.pdf");

let counter = 0;
export function uniqueTitle(prefix: string): string {
  counter += 1;
  return `${prefix} ${Date.now().toString(36)}-${counter}`;
}

/** Create a case through the API (demo mode needs no auth). */
export async function createCaseViaApi(
  request: APIRequestContext,
  title: string,
): Promise<string> {
  const response = await request.post("/api/v1/cases", { data: { title } });
  expect(response.status()).toBe(201);
  const body = (await response.json()) as { id: string };
  return body.id;
}

/** Open the create-case dialog and submit (UI path). Returns the new case title. */
export async function createCaseViaUi(page: Page, prefix: string): Promise<string> {
  const title = uniqueTitle(prefix);
  await page.getByRole("button", { name: "New case" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Case title", { exact: true }).fill(title);
  await dialog.getByRole("button", { name: /^Create case$/ }).click();
  await expect(dialog).toBeHidden();
  return title;
}

/** Navigate to the case whose card shows `title`. */
export async function openCase(page: Page, title: string): Promise<void> {
  await page.getByRole("link", { name: new RegExp(title) }).first().click();
  await expect(page.getByRole("navigation", { name: "Case sections" })).toBeVisible();
}

/** Upload a file through the dropzone input and wait for the POST to answer. */
export async function uploadFile(page: Page, filePath: string, fileName: string): Promise<void> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" && response.url().includes("/documents"),
  );
  await page.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: "application/pdf",
    buffer: require("fs").readFileSync(filePath),
  });
  return await responsePromise.then(() => undefined);
}

/** Wait until the documents table shows the given status for a filename. */
export async function expectDocumentStatus(page: Page, fileName: string, status: RegExp): Promise<void> {
  const row = page.getByRole("cell", { name: fileName }).locator("..");
  await expect(row).toContainText(status, { timeout: 30_000 });
}

export async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
}

export { expect };
