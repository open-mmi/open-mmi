"use strict";

const { defineConfig } = require("@playwright/test");

const executablePath = process.env.OPEN_MMI_PLAYWRIGHT_EXECUTABLE || undefined;

module.exports = defineConfig({
  testDir: "./tests/browser",
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [["line"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : "list",
  use: {
    headless: true,
    launchOptions: executablePath ? { executablePath } : {},
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "dashboard-800x480",
      use: { browserName: "chromium", viewport: { width: 800, height: 480 } },
    },
  ],
});
