import { test, expect } from "@playwright/test";

test("guided catalog review workspace is visible", async ({ page }) => {
  await page.goto("/workspace/documents");
  await expect(page.getByRole("main").getByText("Document intelligence", { exact: true })).toBeVisible();
  await expect(page.getByText("Field evidence", { exact: true })).toBeVisible();
  await page.goto("/workspace/publish");
  await expect(page.getByRole("main").getByText("Publish center", { exact: true })).toBeVisible();
});
