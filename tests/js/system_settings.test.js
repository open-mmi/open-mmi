"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const settings = require("../../ui/web_dashboard/static/system-settings.js");

test("system settings escape server-provided values", () => {
  assert.equal(settings.escapeHtml('<script>"x"</script>'), "&lt;script&gt;&quot;x&quot;&lt;/script&gt;");
});

test("system and Jellyfin templates never contain stored secrets", () => {
  const listeners = {};
  const panel = { innerHTML: "", appendChild() {} };
  const active = { dataset: { openmmiSettingsSection: "system" } };
  const document = {
    body: {},
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
  const api = {
    async getJson() {
      return {
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
    },
    async postJson() { return { ok: true }; },
  };
  const controller = settings.createController({ window, document, api });
  return controller.refresh().then(() => {
    const systemHtml = controller.systemTemplate();
    assert.match(systemHtml, /Default interface/);
    assert.match(systemHtml, /Open Open MMI at login/);
    assert.match(systemHtml, /data-openmmi-system-settings-ready="true"/);
    assert.match(systemHtml, /Dashboard version/);
    assert.match(systemHtml, /frontend-abc/);
    assert.match(systemHtml, /server-def/);
    assert.match(systemHtml, /reload ready/);
    assert.doesNotMatch(systemHtml, /Enable or disable the dashboard systemd user service/);
    active.dataset.openmmiSettingsSection = "media";
    const jellyfinHtml = controller.jellyfinTemplate();
    assert.match(jellyfinHtml, /server-side credentials/);
    assert.doesNotMatch(jellyfinHtml, /secret-value|saved-password|saved-token/);
    assert.match(jellyfinHtml, /Leave blank to keep saved password/);
  });
});


test("frontend version states are presented as user-facing update labels", () => {
  assert.equal(settings.createController ? true : false, true);
  const labels = {
    current: "up to date",
    reloading: "applying update",
    "update-ready": "reload ready",
    "mismatch-after-reload": "reload required",
    reconnecting: "checking…",
    unavailable: "unavailable",
  };
  // Exercise the exported helper through a minimal controller instance.
  const document = { body: {}, querySelector() { return null; }, addEventListener() {} };
  const window = { document, addEventListener() {}, requestAnimationFrame(cb) { cb(); }, MutationObserver: class { observe() {} }, FormData: class {}, setTimeout };
  const api = { async getJson() { return {}; }, async postJson() { return {}; } };
  const controller = settings.createController({ window, document, api });
  for (const [state, label] of Object.entries(labels)) {
    assert.equal(controller.frontendVersionStateLabel(state), label);
  }
});
