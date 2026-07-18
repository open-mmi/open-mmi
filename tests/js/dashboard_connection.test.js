"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const connection = require("../../ui/web_dashboard/static/dashboard-connection.js");

function createHarness() {
  const apiListeners = new Set();
  const windowListeners = new Map();
  const documentListeners = new Map();
  const events = [];
  const timers = [];
  const control = {
    disabled: false,
    dataset: {},
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] ?? null; },
    removeAttribute(name) { delete this.attributes[name]; },
  };
  const message = { textContent: "" };
  const notice = {
    hidden: true,
    querySelector(selector) {
      return selector === "[data-openmmi-dashboard-connection-message]" ? message : null;
    },
  };
  const document = {
    hidden: false,
    visibilityState: "visible",
    body: { dataset: {} },
    querySelector(selector) {
      return selector === "#openMmiDashboardConnectionNotice" ? notice : null;
    },
    querySelectorAll() { return [control]; },
    addEventListener(name, callback) { documentListeners.set(name, callback); },
    removeEventListener(name) { documentListeners.delete(name); },
  };
  const window = {
    document,
    CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
    dispatchEvent(event) { events.push(event); return true; },
    addEventListener(name, callback) { windowListeners.set(name, callback); },
    removeEventListener(name) { windowListeners.delete(name); },
  };
  const scheduler = {
    setTimeout(callback, delay) {
      const timer = { callback, delay, cleared: false };
      timers.push(timer);
      return timer;
    },
    clearTimeout(timer) { if (timer) timer.cleared = true; },
  };
  let healthFailure = null;
  const api = {
    subscribeConnection(listener) { apiListeners.add(listener); return () => apiListeners.delete(listener); },
    async getJson(path) {
      assert.equal(path, "/api/health");
      if (healthFailure) {
        const error = healthFailure;
        for (const listener of apiListeners) listener({ reachable: false, path, error });
        throw error;
      }
      for (const listener of apiListeners) listener({ reachable: true, path, status: 200 });
      return { ok: true };
    },
  };
  return {
    api, control, document, documentListeners, events, message, notice, scheduler, timers, window, windowListeners,
    setHealthFailure(error) { healthFailure = error; },
    emitApi(detail) { for (const listener of apiListeners) listener(detail); },
  };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("shared dashboard connection reaches ready and emits compatibility recovery event", async () => {
  const harness = createHarness();
  const controller = connection.createController({
    api: harness.api,
    document: harness.document,
    window: harness.window,
    scheduler: harness.scheduler,
    retryDelaysMs: [10, 20],
  });

  assert.equal(controller.start(), true);
  await settle();
  assert.equal(controller.snapshot().state, "ready");
  assert.equal(harness.document.body.dataset.openmmiDashboardConnection, "ready");
  assert.equal(harness.notice.hidden, true);
  assert.equal(harness.events.some((event) => event.type === "openmmi:dashboardconnected"), true);
  assert.equal(controller.stop(), true);
});

test("network loss disables live controls and schedules one bounded retry", async () => {
  const harness = createHarness();
  const controller = connection.createController({
    api: harness.api,
    document: harness.document,
    window: harness.window,
    scheduler: harness.scheduler,
    retryDelaysMs: [1000, 2000],
  });
  controller.start();
  await settle();

  harness.emitApi({ reachable: false, path: "/api/status", error: new Error("offline") });
  assert.equal(controller.snapshot().state, "reconnecting");
  assert.equal(harness.control.disabled, true);
  assert.equal(harness.control.dataset.openmmiConnectionDisabled, "true");
  assert.equal(harness.notice.hidden, false);
  assert.match(harness.message.textContent, /reconnecting/i);
  assert.equal(harness.timers.filter((timer) => !timer.cleared).length, 1);
  assert.equal(harness.timers.find((timer) => !timer.cleared).delay, 1000);

  harness.emitApi({ reachable: false, path: "/api/status", error: new Error("still offline") });
  assert.equal(harness.timers.filter((timer) => !timer.cleared).length, 1, "duplicate failures must not multiply retry timers");
});

test("same-build service recovery restores controls without navigation or reload ownership", async () => {
  const harness = createHarness();
  const controller = connection.createController({
    api: harness.api,
    document: harness.document,
    window: harness.window,
    scheduler: harness.scheduler,
    retryDelaysMs: [1],
  });
  controller.start();
  await settle();
  harness.emitApi({ reachable: false, error: new Error("offline") });
  harness.emitApi({ reachable: true, path: "/api/health", status: 200 });

  assert.equal(controller.snapshot().state, "ready");
  assert.equal(controller.snapshot().metrics.recoveries, 1);
  assert.equal(harness.control.disabled, false);
  assert.equal(harness.control.dataset.openmmiConnectionDisabled, undefined);
  assert.equal(harness.events.filter((event) => event.type === "openmmi:dashboardconnected").length, 2);
});

test("hidden documents pause retries and visibility restoration probes immediately", async () => {
  const harness = createHarness();
  harness.setHealthFailure(new Error("offline"));
  const controller = connection.createController({
    api: harness.api,
    document: harness.document,
    window: harness.window,
    scheduler: harness.scheduler,
    retryDelaysMs: [25],
  });
  controller.start();
  await settle();
  assert.equal(controller.snapshot().state, "unavailable");

  harness.document.hidden = true;
  harness.document.visibilityState = "hidden";
  harness.documentListeners.get("visibilitychange")();
  assert.equal(harness.timers.filter((timer) => !timer.cleared).length, 0);

  harness.setHealthFailure(null);
  harness.document.hidden = false;
  harness.document.visibilityState = "visible";
  harness.documentListeners.get("visibilitychange")();
  await settle();
  assert.equal(controller.snapshot().state, "ready");
});
