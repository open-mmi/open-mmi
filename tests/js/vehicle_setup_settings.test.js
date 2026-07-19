"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const vehicleSetup = require("../../ui/web_dashboard/static/vehicle-setup-settings.js");

function payload() {
  return {
    api_version: 1,
    read_only: true,
    runtime_mode: "single",
    active: {
      state: "ready",
      errors: [],
      vehicle: { source: "maintained", id: "seat_1p", revision: "sha256:profile" },
      bindings: { source: "maintained", id: "default", revision: "sha256:bindings" },
      active_bus: "comfort",
      interface: "can0",
      interface_present: false,
      configuration_revision: "sha256:configuration",
      loaded: null,
    },
    catalogue: {
      development_mode: false,
      issues: [],
      profiles: [
        {
          source: "maintained", id: "seat_1p", display_name: "Seat 1P", valid: true,
          default_bus: "comfort", buses: [{ name: "comfort", interface: "can0", bitrate: 100000 }],
          validation: { valid: true, errors: [], warnings: [] },
        },
        {
          source: "custom", id: "my-seat", display_name: "My <Seat>", valid: true,
          default_bus: "comfort", buses: [{ name: "comfort", interface: "can1", bitrate: 100000 }],
          validation: { valid: true, errors: [], warnings: [] },
        },
        {
          source: "custom", id: "broken", display_name: "Broken", valid: false,
          validation: { valid: false, errors: [{ code: "invalid-document" }], warnings: [] },
        },
      ],
      bindings: [
        {
          source: "maintained", id: "default", display_name: "Default", valid: true,
          binding_count: 12,
          validation: { valid: true, errors: [], warnings: [{ code: "legacy-action-schema" }] },
        },
        {
          source: "custom", id: "my-controls", display_name: "My controls", valid: true,
          binding_count: 11,
          validation: { valid: true, errors: [], warnings: [] },
        },
      ],
    },
    compatibility: {
      emitted_and_bound: ["play_pause", "volume_up"],
      emitted_unbound: [],
      bound_unemitted: ["stop_playback"],
      duplicate_emitted: [],
    },
    interfaces: [],
  };
}

function fixture(options = {}) {
  const listeners = {};
  const calls = [];
  const panel = { innerHTML: "" };
  const active = { dataset: { openmmiSettingsSection: "vehicle-setup" } };
  const document = {
    querySelector(selector) {
      if (selector === "[data-openmmi-settings-section].active") return active;
      if (selector === "#openmmiSettingsPanel") return panel;
      return null;
    },
    addEventListener(name, callback) { listeners[name] = callback; },
  };
  const window = {
    document,
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); },
  };
  const api = {
    async getJson(path) {
      calls.push(["GET", path]);
      if (options.error) throw new Error(options.error);
      return payload();
    },
    async postJson(path, body) {
      calls.push(["POST", path, body]);
      throw new Error("Vehicle setup status must not POST");
    },
  };
  return { active, api, calls, document, listeners, panel, window };
}

test("vehicle setup renders maintained and custom draft choices without apply", async () => {
  const state = fixture();
  const controller = vehicleSetup.createController(state);
  await controller.refresh();
  const html = controller.template();

  assert.match(html, /Vehicle setup/);
  assert.match(html, /Current active setup is ready/);
  assert.match(html, /Seat 1P/);
  assert.match(html, /Default · Maintained/);
  assert.match(html, /Maintained/);
  assert.match(html, /Custom/);
  assert.match(html, /My &lt;Seat&gt;/);
  assert.match(html, /value="custom:broken" disabled/);
  assert.match(html, /can0 · not detected/);
  assert.match(html, /100 kbit\/s/);
  assert.match(html, /Review and apply/);
  assert.match(html, /data-testid="vehicle-setup-review" disabled/);
  assert.deepEqual(state.calls, [["GET", "/api/system/vehicle-setup"]]);
  assert.equal(state.calls.some((call) => call[0] === "POST"), false);
});

test("profile and bindings changes remain an unapplied in-memory draft", async () => {
  const state = fixture();
  const controller = vehicleSetup.createController(state);
  await controller.refresh();

  assert.equal(controller.setDraft("vehicle", "custom:my-seat"), true);
  assert.equal(controller.setDraft("bindings", "custom:my-controls"), true);
  assert.equal(controller.draftDiffers(), true);
  assert.deepEqual(controller.draft(), {
    vehicle: "custom:my-seat",
    bindings: "custom:my-controls",
  });
  assert.match(controller.template(), /Changes not applied/);
  assert.match(controller.template(), /can1/);
  assert.equal(controller.setDraft("vehicle", "custom:broken"), false);
  assert.equal(state.calls.some((call) => call[0] === "POST"), false);
});

test("endpoint failures stay inside the vehicle setup panel", async () => {
  const state = fixture({ error: "catalogue unavailable" });
  const controller = vehicleSetup.createController(state);
  await assert.rejects(controller.refresh(), /catalogue unavailable/);
  assert.match(controller.template(), /catalogue unavailable/);
  assert.match(controller.template(), /data-testid="vehicle-setup-refresh"/);
});

test("identity helpers never accept path-shaped input", () => {
  assert.equal(vehicleSetup.identityKey({ source: "maintained", id: "seat_1p" }), "maintained:seat_1p");
  assert.equal(vehicleSetup.identityKey({ source: "maintained", id: "../../tmp" }), "");
  assert.equal(vehicleSetup.escapeHtml('../../tmp/<script>'), "../../tmp/&lt;script&gt;");
});
