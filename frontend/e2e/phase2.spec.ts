import { test, expect } from "@playwright/test";

test.describe("CatalogForge Phase 2 enterprise views", () => {
  test("workspace dashboard exposes a tenant-aware operational shell", async ({ page }) => {
    await page.goto("/workspace/dashboard");
    await expect(page.getByText("Synthetic demo", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("main").getByText("Operations overview", { exact: true })).toBeVisible();
    await expect(page.getByRole("main").getByText("Products extracted", { exact: true })).toBeVisible();
  });

  test("source intake and document evidence use the live workflow surfaces", async ({ page }) => {
    await page.goto("/workspace/source-intake");
    await expect(page.getByRole("main").getByText("Media and Source Intake Center", { exact: true })).toBeVisible();
    await expect(page.getByText("What local mode implements", { exact: true })).toBeVisible();
    await page.goto("/workspace/documents");
    await expect(page.getByRole("main").getByText("Document intelligence", { exact: true })).toBeVisible();
    await expect(page.getByText("Field evidence", { exact: true })).toBeVisible();
  });

  test("governance workflows are discoverable", async ({ page }) => {
    await page.goto("/workspace/change-sets");
    await expect(page.getByRole("main").getByText("Change Set Detail", { exact: true })).toBeVisible();
    await page.goto("/workspace/lineage");
    await expect(page.getByRole("main").getByText("Data Lineage Explorer", { exact: true })).toBeVisible();
    await page.goto("/workspace/governance");
    await expect(page.getByRole("main").getByText("Security & Governance Center", { exact: true })).toBeVisible();
  });

  test("command palette provides safe, keyboard-accessible navigation", async ({ page }) => {
    await page.goto("/workspace/dashboard");
    await page.keyboard.press("Control+K");
    await expect(page.getByPlaceholder("Search products, vendors, documents, or actions…")).toBeVisible();
    await expect(page.getByText("Open Intake Inbox", { exact: true })).toBeVisible();
  });
});
