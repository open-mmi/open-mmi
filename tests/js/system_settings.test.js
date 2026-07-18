"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const settings = require("../../ui/web_dashboard/static/system-settings.js");

function fixture(options = {}) {
  const listeners = {};
  const panel = { innerHTML: "", appendChild() {}, querySelector() { return null; } };
  const active = { dataset: { openmmiSettingsSection: options.section || "system" } };
  const document = {
    body: {},
    activeElement: null,
    querySelector(selector) {
      if (selector === "[data-openmmi-settings-section].active") return active;
      if (selector === "#openmmiSettingsPanel") return panel;
      return null;
    },
    addEventListener(name, callback) { listeners[name] = callback; },
    createElement() { return { innerHTML: "", id: "" }; },
  };
  const window = {
    document,
    __openMmiFrontendVersionController: {
      snapshot() {
        return { loadedId: "frontend-abc", serverId: "server-def", state: "update-ready" };
      },
    },
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); },
    MutationObserver: class { observe() {} },
    FormData: class {},
    setTimeout,
  };
  const systemPayload = {
    launcher: { default_ui: "web", open_at_login: true, service_active: true, dashboard_reachable: true },
    jellyfin: {
      configured: true,
      url: "https://media.test",
      username: "driver",
      password_configured: true,
      token_configured: false,
      path: "/home/user/.config/open-mmi/dashboard.env",
    },
  };
  const updatePayload = {
    api_version: 1,
    read_only: true,
    installed: { managed: true, version: "v1-runtime-42-gabc1234", commit: "abc1234def56" },
    channel: "development",
    source: { configured: true, state: "ready", clean: true, branch: "main", upstream: "origin/main" },
    update: {
      state: "not-checked", checked_at: null, available_version: "", available_commit: "",
      remote_differs: null, update_available: null, error: "",
    },
    readiness: { state: "ready", blockers: [] },
  };
  const calls = [];
  const api = {
    async getJson(path) {
      calls.push(["GET", path]);
      if (path === "/api/system/settings") return systemPayload;
      if (path === "/api/system/update-status") return updatePayload;
      throw new Error(`Unexpected GET ${path}`);
    },
    async postJson(path, body) {
      calls.push(["POST", path, body]);
      if (path === "/api/system/update-check") {
        return {
          ...updatePayload,
          update: {
            state: "update-available",
            checked_at: "2026-07-18T14:32:00+00:00",
            available_version: "def5678abc90",
            available_commit: "def5678abc901234567890123456789012345678",
            remote_differs: true,
            update_available: true,
            error: "",
          },
        };
      }
      return { ok: true };
    },
  };
  return { active, api, calls, document, panel, systemPayload, updatePayload, window };
}

test("system settings escape server-provided values", () => {
  assert.equal(settings.escapeHtml('<script>"x"</script>'), "&lt;script&gt;&quot;x&quot;&lt;/script&gt;");
});

test("system and Jellyfin templates expose read-only update state without stored secrets", async () => {
  const state = fixture();
  const controller = settings.createController(state);
  await controller.refresh();
  const systemHtml = controller.systemTemplate();
  assert.match(systemHtml, /Default interface/);
  assert.match(systemHtml, /Open Open MMI at login/);
  assert.match(systemHtml, /data-openmmi-system-settings-ready="true"/);
  assert.match(systemHtml, /Dashboard version/);
  assert.match(systemHtml, /frontend-abc/);
  assert.match(systemHtml, /server-def/);
  assert.match(systemHtml, /reload ready/);
  assert.match(systemHtml, /Software updates/);
  assert.match(systemHtml, /v1-runtime-42-gabc1234/);
  assert.match(systemHtml, /development/);
  assert.match(systemHtml, /not checked/);
  assert.match(systemHtml, /Repository health/);
  assert.match(systemHtml, /Check for updates/);
  assert.doesNotMatch(systemHtml, /Install update|Rollback|repository_path|https:\/\/github/);
  assert.deepEqual(state.calls.slice(0, 2), [
    ["GET", "/api/system/settings"],
    ["GET", "/api/system/update-status"],
  ]);

  state.active.dataset.openmmiSettingsSection = "media";
  const jellyfinHtml = controller.jellyfinTemplate();
  assert.match(jellyfinHtml, /server-side credentials/);
  assert.doesNotMatch(jellyfinHtml, /secret-value|saved-password|saved-token/);
  assert.match(jellyfinHtml, /Leave blank to keep saved password/);
});

test("manual update check sends only fixed confirmation and refreshes the panel", async () => {
  const state = fixture();
  const controller = settings.createController(state);
  await controller.refresh();
  const payload = await controller.checkForUpdates();
  assert.equal(payload.update.state, "update-available");
  assert.deepEqual(state.calls.at(-1), ["POST", "/api/system/update-check", { confirm: true }]);
  const html = controller.systemTemplate();
  assert.match(html, /update available/);
  assert.match(html, /def5678abc90/);
  assert.match(html, /2026-07-18 14:32:00 UTC/);
});

test("frontend and update states use conservative user-facing labels", () => {
  const state = fixture();
  const controller = settings.createController(state);
  const frontendLabels = {
    current: "up to date",
    reloading: "applying update",
    "update-ready": "reload ready",
    "mismatch-after-reload": "reload required",
    reconnecting: "checking…",
    unavailable: "unavailable",
  };
  for (const [value, label] of Object.entries(frontendLabels)) {
    assert.equal(controller.frontendVersionStateLabel(value), label);
  }
  assert.equal(controller.updateStateLabel("remote-different"), "remote differs");
  assert.equal(controller.updateStateLabel("update-available"), "update available");
  assert.equal(controller.repositoryStateLabel("dirty"), "local changes");
  assert.equal(controller.checkedAtLabel(null), "never");
});
