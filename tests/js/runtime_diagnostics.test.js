"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const runtime = require("../../ui/web_dashboard/static/runtime-diagnostics.js");

function thermalFixture(overrides = {}) {
  return Object.assign({
    api_version: 1,
    sampled_at: "2026-07-16T22:29:54+00:00",
    cpu: {
      average_mhz: 400,
      current_min_mhz: 399,
      current_max_mhz: 400,
      minimum_mhz: 400,
      maximum_mhz: 3500,
      load_1m: 6.21,
      load_high: true,
      near_minimum: true,
      cpus: [],
      intel_pstate: {},
    },
    thermal: {
      summary: "thermal-limit-active",
      selected_zone: "GEN4",
      temperature_c: 52.5,
      relevant_trip: { temperature_c: 48.05, types: ["active", "passive"], margin_c: -4.45 },
      zones: [],
      cooling_devices: [],
    },
    power: {
      ac_online: true,
      battery_status: "Not charging",
      capacity_percent: 65,
      charging_state: "not-charging",
      supplies: [],
    },
  }, overrides);
}

test("thermal performance limit requires repeated high-load minimum-clock samples", () => {
  const sample = thermalFixture();
  assert.equal(runtime.deriveSystemState(sample, 1).code, "thermal-limit-active");
  assert.equal(runtime.deriveSystemState(sample, 2).code, "performance-limited-temperature");

  const idle = thermalFixture({
    cpu: Object.assign({}, sample.cpu, { load_high: false }),
    thermal: Object.assign({}, sample.thermal, { summary: "normal", temperature_c: 42 }),
  });
  assert.equal(runtime.deriveSystemState(idle, 0).code, "normal");
});

test("session history tracks observed clock and platform temperature ranges", () => {
  let history = runtime.updateHistory(null, thermalFixture());
  history = runtime.updateHistory(history, thermalFixture({
    cpu: Object.assign({}, thermalFixture().cpu, { current_min_mhz: 800, current_max_mhz: 3500 }),
    thermal: Object.assign({}, thermalFixture().thermal, { temperature_c: 44 }),
  }));
  assert.deepEqual(history, {
    cpuMinMhz: 399,
    cpuMaxMhz: 3500,
    tempMinC: 44,
    tempMaxC: 52.5,
  });
});

test("charging suspension remains distinct from disconnected AC and charger capacity", () => {
  const sample = thermalFixture();
  assert.equal(runtime.chargingLabel(sample.power), "AC connected — not charging");
  const values = runtime.summaryValues(sample, runtime.updateHistory(null, sample), 2);
  assert.equal(values["power.ac"], "Yes");
  assert.equal(values["power.state"], "AC connected — not charging");
  assert.doesNotMatch(JSON.stringify(values), /charger|53\.9 W/i);
});

test("polling runs only while Diagnostics is selected and visible", async () => {
  let selected = "diagnostics";
  let pageActive = true;
  let runtimeHost = null;
  let requestCount = 0;
  let scheduled = null;

  const panel = {
    querySelector(selector) {
      if (selector === ".openmmi-settings-panel-head") return { after(node) { runtimeHost = node; } };
      return null;
    },
    prepend(node) { runtimeHost = node; },
  };
  const document = {
    hidden: false,
    querySelector(selector) {
      if (selector === "[data-openmmi-settings-section].active") {
        return { dataset: { openmmiSettingsSection: selected } };
      }
      if (selector === "#pageSettings.active") return pageActive ? {} : null;
      if (selector === "#openmmiSettingsPanel") return panel;
      if (selector === "#openMmiRuntimeDiagnostics") return runtimeHost;
      return null;
    },
    createElement() {
      return {
        id: "",
        className: "",
        dataset: {},
        setAttribute() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
      };
    },
    addEventListener() {},
    removeEventListener() {},
  };
  const scheduler = {
    setTimeout(callback) { scheduled = callback; return 1; },
    clearTimeout() { scheduled = null; },
  };
  const window = {
    document,
    CustomEvent: class { constructor(name, options) { this.type = name; this.detail = options?.detail; } },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {},
    requestAnimationFrame() {},
  };
  const api = {
    async getJson(path) {
      assert.equal(path, runtime.ENDPOINT);
      requestCount += 1;
      return thermalFixture();
    },
  };

  const controller = runtime.createController({ window, document, scheduler, api, intervalMs: 100 });
  controller.sync();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requestCount, 1);
  assert.equal(typeof scheduled, "function");
  assert.equal(controller.snapshot().constrainedSamples, 1);
  controller.sync();
  assert.equal(controller.snapshot().constrainedSamples, 1);

  selected = "system";
  controller.sync();
  assert.equal(scheduled, null);

  selected = "diagnostics";
  document.hidden = true;
  controller.sync();
  assert.equal(requestCount, 1);

  document.hidden = false;
  controller.sync();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requestCount, 2);

  pageActive = false;
  controller.sync();
  assert.equal(scheduled, null);
});
