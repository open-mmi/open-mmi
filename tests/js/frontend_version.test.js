"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const frontendVersion = require("../../ui/web_dashboard/static/frontend-version.js");

function storage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) { return values.get(key) || null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

function environment({ activeEditable = false, attemptedTarget = "" } = {}) {
  const listeners = new Map();
  const notice = {
    hidden: true,
    message: { textContent: "" },
    button: {
      addEventListener(name, callback) { listeners.set(`button:${name}`, callback); },
      removeEventListener() {},
    },
    querySelector(selector) {
      if (selector.includes("message")) return this.message;
      if (selector.includes("reload")) return this.button;
      return null;
    },
  };
  const activeElement = activeEditable
    ? { closest(selector) { return selector.includes("input") ? this : null; } }
    : { closest() { return null; } };
  const documentRef = {
    hidden: false,
    activeElement,
    querySelector(selector) {
      if (selector === "#openMmiUpdateNotice") return notice;
      if (selector.includes("data-openmmi-dirty")) return null;
      return null;
    },
    addEventListener(name, callback) { listeners.set(`document:${name}`, callback); },
    removeEventListener() {},
  };
  const replacements = [];
  const sessionStorage = storage(attemptedTarget ? {
    [frontendVersion.RELOAD_TARGET_KEY]: attemptedTarget,
  } : {});
  const windowRef = {
    document: documentRef,
    sessionStorage,
    location: {
      href: "http://127.0.0.1:8765/?page=home",
      replace(url) { replacements.push(url); },
    },
    addEventListener(name, callback) { listeners.set(`window:${name}`, callback); },
    removeEventListener() {},
    dispatchEvent() {},
    CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init.detail; } },
  };
  const timers = [];
  const scheduler = {
    setTimeout(callback, delay) { timers.push({ callback, delay }); return timers.length; },
    clearTimeout() {},
  };
  return { documentRef, listeners, notice, replacements, scheduler, sessionStorage, timers, windowRef };
}

test("equal frontend identities remain current without reload", async () => {
  const env = environment();
  const controller = frontendVersion.createController({
    ...env,
    loadedId: "build-a",
    fetchJson: async () => ({ frontend_id: "build-a", reload_supported: true }),
    intervalMs: 60000,
  });
  await controller.checkNow();
  assert.equal(controller.snapshot().state, "current");
  assert.deepEqual(env.replacements, []);
  assert.equal(env.notice.hidden, true);
  assert.equal(env.timers.at(-1).delay, 60000);
});

test("a changed build triggers one version-targeted reload", () => {
  const env = environment();
  const controller = frontendVersion.createController({ ...env, loadedId: "build-a" });
  controller.reconcile({ frontend_id: "build-b", reload_supported: true });
  assert.equal(controller.snapshot().state, "reloading");
  assert.equal(env.replacements.length, 1);
  assert.match(env.replacements[0], /openmmi_frontend=build-b/);
  assert.equal(env.sessionStorage.getItem(frontendVersion.RELOAD_TARGET_KEY), "build-b");
});

test("the same failed target cannot create a reload loop", () => {
  const env = environment({ attemptedTarget: "build-b" });
  const controller = frontendVersion.createController({ ...env, loadedId: "build-a" });
  controller.reconcile({ frontend_id: "build-b", reload_supported: true });
  assert.equal(controller.snapshot().state, "mismatch-after-reload");
  assert.deepEqual(env.replacements, []);
  assert.equal(env.notice.hidden, false);
  assert.match(env.notice.message.textContent, /did not load/i);
});

test("active editing defers automatic reload and allows explicit acceptance", () => {
  const env = environment({ activeEditable: true });
  const controller = frontendVersion.createController({ ...env, loadedId: "build-a" });
  controller.reconcile({ frontend_id: "build-b", reload_supported: true });
  assert.equal(controller.snapshot().state, "update-ready");
  assert.deepEqual(env.replacements, []);
  assert.match(env.notice.message.textContent, /finish editing/i);
  assert.equal(controller.reloadNow(), true);
  assert.equal(env.replacements.length, 1);
});

test("hidden documents do not keep a periodic version timer", async () => {
  const env = environment();
  env.documentRef.hidden = true;
  const controller = frontendVersion.createController({
    ...env,
    loadedId: "build-a",
    fetchJson: async () => ({ frontend_id: "build-a", reload_supported: true }),
  });
  await controller.checkNow();
  assert.equal(env.timers.length, 0);
});

test("malformed version responses never reload", () => {
  const env = environment();
  const controller = frontendVersion.createController({ ...env, loadedId: "build-a" });
  controller.reconcile({ ok: true });
  assert.equal(controller.snapshot().state, "unavailable");
  assert.deepEqual(env.replacements, []);
});
