"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const api = require("../../ui/web_dashboard/static/api.js");
const preferences = require("../../ui/web_dashboard/static/preferences.js");

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

test("preferences safely reads, writes, and removes JSON", () => {
  const storage = memoryStorage();
  assert.deepEqual(preferences.readObject("missing", { fallback: true }, storage), { fallback: true });
  assert.equal(preferences.writeJson("settings", { speedUnit: "kmh" }, storage), true);
  assert.deepEqual(preferences.readObject("settings", {}, storage), { speedUnit: "kmh" });
  assert.equal(preferences.remove("settings", storage), true);
  assert.deepEqual(preferences.readObject("settings", {}, storage), {});
});

test("preferences tolerate malformed and unavailable storage", () => {
  const malformed = memoryStorage({ broken: "{" });
  assert.deepEqual(preferences.readObject("broken", { safe: true }, malformed), { safe: true });
  const denied = {
    getItem() { throw new Error("denied"); },
    setItem() { throw new Error("denied"); },
    removeItem() { throw new Error("denied"); },
  };
  assert.deepEqual(preferences.readObject("x", { safe: true }, denied), { safe: true });
  assert.equal(preferences.writeJson("x", {}, denied), false);
  assert.equal(preferences.remove("x", denied), false);
});

test("dashboard settings merge defaults", () => {
  const storage = memoryStorage({
    [preferences.DASHBOARD_SETTINGS_KEY]: JSON.stringify({ speedUnit: "kmh" }),
  });
  assert.deepEqual(
    preferences.readDashboardSettings({ speedUnit: "mph", tempUnit: "c" }, storage),
    { speedUnit: "kmh", tempUnit: "c" },
  );
});

test("API GET requests are no-store and parse JSON", async () => {
  let observed = null;
  global.fetch = async (path, init) => {
    observed = { path, init };
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  };
  assert.deepEqual(await api.getJson("/api/status"), { ok: true });
  assert.equal(observed.path, "/api/status");
  assert.equal(observed.init.cache, "no-store");
});

test("API POST requests preserve same-origin JSON semantics", async () => {
  let observed = null;
  global.fetch = async (path, init) => {
    observed = { path, init };
    return { ok: true, status: 200, json: async () => ({ performed_action: "play" }) };
  };
  const payload = await api.postJson("/api/bluetooth/control", { action: "play" });
  assert.deepEqual(payload, { performed_action: "play" });
  assert.equal(observed.init.method, "POST");
  assert.equal(observed.init.credentials, "same-origin");
  assert.equal(observed.init.headers["Content-Type"], "application/json");
  assert.equal(observed.init.body, JSON.stringify({ action: "play" }));
});

test("API errors expose status and server payload", async () => {
  global.fetch = async () => ({
    ok: false,
    status: 403,
    json: async () => ({ error: "denied" }),
  });
  await assert.rejects(
    () => api.getJson("/api/private", { usePayloadError: true }),
    (error) => error.message === "denied" && error.status === 403,
  );
});
