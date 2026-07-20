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

function previewPayload() {
  return {
    api_version: 1,
    read_only: true,
    apply_available: false,
    state: "ready",
    expected_configuration_revision: "sha256:configuration",
    target_configuration_revision: "sha256:target",
    target: {
      vehicle: { source: "custom", id: "my-seat", revision: "sha256:custom-profile" },
      bindings: { source: "custom", id: "my-controls", revision: "sha256:custom-bindings" },
      runtime: { mode: "single", active_bus: "comfort", buses: { comfort: { interface: "can1" } } },
    },
    active_bus: { name: "comfort", interface: "can1", profile_interface: "can1", bitrate: 100000, provisioning: "manual" },
    interface: { name: "can1", present: false, up: false, configured_bitrate: null },
    compatibility: {
      emitted_and_bound: ["play_pause"], emitted_unbound: [],
      bound_unemitted: ["stop_playback"], duplicate_emitted: [],
    },
    validation: {
      valid: true,
      errors: [],
      warnings: [{ code: "bindings-unused", message: "1 binding is not emitted by the profile" }],
    },
    plan: {
      changes: [
        {
          field: "vehicle",
          from: { source: "maintained", id: "seat_1p", revision: "sha256:profile" },
          to: { source: "custom", id: "my-seat", revision: "sha256:custom-profile" },
        },
        { field: "bindings", from: { source: "maintained", id: "default" }, to: { source: "custom", id: "my-controls" } },
        { field: "interface", from: "can0", to: "can1" },
      ],
      effects: {
        write_canonical_configuration: true,
        write_systemd_runtime: true,
        write_udev_rules: true,
        reload_user_manager: true,
        reload_udev: true,
        restart_can_service: true,
      },
    },
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
      if (options.previewError) throw new Error(options.previewError);
      if (path !== vehicleSetup.PREVIEW_ENDPOINT) throw new Error("Unexpected vehicle setup POST");
      return options.preview || previewPayload();
    },
  };
  return { active, api, calls, document, listeners, panel, window };
}

test("vehicle setup renders maintained and custom draft choices before review", async () => {
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
  assert.match(html, /Review current setup/);
  assert.doesNotMatch(html, /data-testid="vehicle-setup-review" disabled/);
  assert.deepEqual(state.calls, [["GET", "/api/system/vehicle-setup"]]);
  assert.equal(state.calls.some((call) => call[0] === "POST"), false);
});

test("the current setup can be reviewed when no alternative catalogue entry exists", async () => {
  const currentPreview = {
    ...previewPayload(),
    plan: {
      changes: [],
      effects: {
        write_canonical_configuration: false,
        write_systemd_runtime: false,
        write_udev_rules: false,
        reload_user_manager: false,
        reload_udev: false,
        restart_can_service: false,
      },
    },
  };
  const state = fixture({ preview: currentPreview });
  const controller = vehicleSetup.createController(state);
  await controller.refresh();
  assert.equal(controller.draftDiffers(), false);
  await controller.reviewDraft();
  assert.deepEqual(state.calls[1], ["POST", "/api/system/vehicle-setup/preview", {
    vehicle: { source: "maintained", id: "seat_1p" },
    bindings: { source: "maintained", id: "default" },
    runtime: { active_bus: "comfort", buses: { comfort: { interface: "can0" } } },
  }]);
  const html = controller.template();
  assert.match(html, /current setup would remain unchanged/);
  assert.match(html, /No active configuration values would change/);
  assert.match(html, /No service or adapter changes are required/);
  assert.match(html, /data-testid="vehicle-setup-apply" disabled/);
});

test("profile and bindings changes produce an exact read-only review request", async () => {
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
  assert.doesNotMatch(controller.template(), /data-testid="vehicle-setup-review" disabled/);
  assert.equal(controller.setDraft("vehicle", "custom:broken"), false);

  const request = controller.previewRequest();
  assert.deepEqual(request, {
    vehicle: { source: "custom", id: "my-seat" },
    bindings: { source: "custom", id: "my-controls" },
    runtime: { active_bus: "comfort", buses: { comfort: { interface: "can1" } } },
  });
  await controller.reviewDraft();
  assert.deepEqual(state.calls[1], ["POST", "/api/system/vehicle-setup/preview", request]);
  assert.equal(controller.preview().read_only, true);
  const review = controller.template();
  assert.match(review, /Review ready/);
  assert.match(review, /data-testid="vehicle-setup-preview"/);
  assert.match(review, /My &lt;Seat&gt; · Custom/);
  assert.match(review, /can1 · not detected/);
  assert.match(review, /1 binding is not emitted by the profile/);
  assert.match(review, /Restart the CAN service/);
  assert.match(review, /data-testid="vehicle-setup-apply" disabled/);
  assert.doesNotMatch(JSON.stringify(request), /path|command|revision/);
});

test("preview failures remain inline and unsafe capability responses fail closed", async () => {
  const failed = fixture({ previewError: "preview unavailable" });
  const failedController = vehicleSetup.createController(failed);
  await failedController.refresh();
  failedController.setDraft("vehicle", "custom:my-seat");
  await assert.rejects(failedController.reviewDraft(), /preview unavailable/);
  assert.match(failedController.template(), /data-testid="vehicle-setup-preview-error"/);
  assert.match(failedController.template(), /preview unavailable/);

  const unsafe = fixture({ preview: { ...previewPayload(), apply_available: true } });
  const unsafeController = vehicleSetup.createController(unsafe);
  await unsafeController.refresh();
  unsafeController.setDraft("vehicle", "custom:my-seat");
  await assert.rejects(unsafeController.reviewDraft(), /not safely available/);
  assert.equal(unsafeController.preview(), null);
  assert.match(unsafeController.template(), /not safely available/);
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
  assert.deepEqual(vehicleSetup.identityFromKey("custom:my_controls"), { source: "custom", id: "my_controls" });
  assert.equal(vehicleSetup.identityFromKey("custom:../../tmp"), null);
  assert.equal(vehicleSetup.escapeHtml('../../tmp/<script>'), "../../tmp/&lt;script&gt;");
});
