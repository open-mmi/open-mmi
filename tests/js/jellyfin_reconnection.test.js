"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const reconnect = require("../../ui/web_dashboard/static/jellyfin-reconnection.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function fakeEnvironment() {
  const timers = [];
  const listeners = new Map();
  const document = {
    hidden: false,
    addEventListener(type, callback) { listeners.set(`document:${type}`, callback); },
    removeEventListener(type) { listeners.delete(`document:${type}`); },
  };
  const window = {
    document,
    addEventListener(type, callback) { listeners.set(`window:${type}`, callback); },
    removeEventListener(type) { listeners.delete(`window:${type}`); },
  };
  const scheduler = {
    setTimeout(callback, delay) {
      const timer = { callback, delay, cancelled: false };
      timers.push(timer);
      return timer;
    },
    clearTimeout(timer) { if (timer) timer.cancelled = true; },
  };
  return { document, window, scheduler, timers, listeners };
}

function nextTimer(env) {
  return env.timers.find((timer) => !timer.cancelled && !timer.ran);
}

async function runTimer(timer) {
  timer.ran = true;
  await timer.callback();
  await new Promise((resolve) => setImmediate(resolve));
}

test("normaliseProviderState distinguishes ready, retryable and terminal failures", () => {
  assert.equal(reconnect.normaliseProviderState({ configured: false }).state, "configuration-missing");
  assert.equal(reconnect.normaliseProviderState({ configured: true, connection_state: "authentication-error" }).retryable, false);
  assert.equal(reconnect.normaliseProviderState({ configured: true, connection_state: "reconnecting", retryable: true }).state, "reconnecting");
  assert.equal(reconnect.normaliseProviderState({ configured: true, status: "playing" }).state, "ready");
});

test("controller retries with bounded backoff and reports one recovery", async () => {
  const env = fakeEnvironment();
  const responses = [
    { configured: true, connection_state: "reconnecting", retryable: true, subtitle: "offline" },
    { configured: true, connection_state: "reconnecting", retryable: true, subtitle: "offline" },
    { configured: true, connection_state: "ready", status: "ready", subtitle: "online" },
  ];
  const states = [];
  let recovered = 0;
  const controller = reconnect.createController({
    ...env,
    retryDelaysMs: [1000, 2000, 5000],
    readyIntervalMs: 7000,
    requestStatus: async () => responses.shift(),
    onStateChange: (state) => states.push(state),
    onRecovered: () => { recovered += 1; },
  });

  controller.start();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(controller.state.status, "reconnecting");
  assert.equal(nextTimer(env).delay, 1000);

  await runTimer(nextTimer(env));
  assert.equal(controller.state.status, "reconnecting");
  assert.equal(nextTimer(env).delay, 2000);

  await runTimer(nextTimer(env));
  assert.equal(controller.state.status, "ready");
  assert.equal(recovered, 1);
  assert.equal(nextTimer(env).delay, 7000);
  assert.ok(states.some((state) => state.status === "reconnecting"));
});

test("authentication failure does not schedule continuous retries", async () => {
  const env = fakeEnvironment();
  const controller = reconnect.createController({
    ...env,
    requestStatus: async () => ({
      configured: true,
      connection_state: "authentication-error",
      retryable: false,
      subtitle: "credentials rejected",
    }),
  });

  controller.start();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(controller.state.status, "authentication-error");
  assert.equal(nextTimer(env), undefined);
});

test("hidden pages pause retries and visibility restoration performs one immediate check", async () => {
  const env = fakeEnvironment();
  const first = deferred();
  let requests = 0;
  const controller = reconnect.createController({
    ...env,
    requestStatus: async () => {
      requests += 1;
      if (requests === 1) return first.promise;
      return { configured: true, connection_state: "ready", status: "ready" };
    },
  });

  controller.start();
  env.document.hidden = true;
  first.resolve({ configured: true, connection_state: "reconnecting", retryable: true });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(nextTimer(env), undefined);

  env.document.hidden = false;
  env.listeners.get("document:visibilitychange")();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requests, 2);
  assert.equal(controller.state.status, "ready");
});

test("inactive providers do not start or duplicate retries", async () => {
  const env = fakeEnvironment();
  let active = false;
  let requests = 0;
  const controller = reconnect.createController({
    ...env,
    isActive: () => active,
    requestStatus: async () => { requests += 1; return { configured: true, status: "ready" }; },
  });

  controller.start();
  assert.equal(requests, 0);
  active = true;
  env.listeners.get("window:openmmi:pagechange")();
  env.listeners.get("window:openmmi:pagechange")();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requests, 1);
});
