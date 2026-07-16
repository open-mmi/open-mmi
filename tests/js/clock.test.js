"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const clock = require("../../ui/web_dashboard/static/clock.js");
const preferences = require("../../ui/web_dashboard/static/preferences.js");

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

function fakeElement() {
  return {
    dataset: {},
    hidden: false,
    textContent: "",
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
}

test("clock normalises display preferences", () => {
  assert.deepEqual(clock.normaliseSettings(), {
    showClock: true,
    clockFormat: "24h",
    showDate: false,
  });
  assert.deepEqual(clock.normaliseSettings({ showClock: false, clockFormat: "12h", showDate: true }), {
    showClock: false,
    clockFormat: "12h",
    showDate: true,
  });
  assert.equal(clock.normaliseSettings({ clockFormat: "invalid" }).clockFormat, "24h");
});

test("clock formats local 24-hour and 12-hour time with an optional date", () => {
  const value = new Date(2026, 6, 16, 7, 5, 30, 250);
  assert.deepEqual(
    clock.formatClock(value, { clockFormat: "24h" }, "en-GB"),
    { time: "07:05", date: "Thu 16 Jul" },
  );
  assert.deepEqual(
    clock.formatClock(value, { clockFormat: "12h", showDate: true }, "en-GB"),
    { time: "7:05 am", date: "Thu 16 Jul" },
  );
});

test("clock schedules updates at the next minute boundary", () => {
  assert.equal(clock.millisecondsUntilNextMinute(new Date(2026, 6, 16, 7, 5, 0, 0)), 60000);
  assert.equal(clock.millisecondsUntilNextMinute(new Date(2026, 6, 16, 7, 5, 30, 250)), 29750);
  assert.equal(clock.millisecondsUntilNextMinute(new Date(2026, 6, 16, 7, 5, 59, 999)), 1);
});

test("clock controller reuses the shared element and preserves unrelated settings", () => {
  const clockElement = fakeElement();
  const timeElement = fakeElement();
  const valueElement = fakeElement();
  const dateElement = fakeElement();
  const elements = {
    "#openMmiClock": clockElement,
    "#openMmiClockTime": timeElement,
    "#openMmiClockValue": valueElement,
    "#openMmiClockDate": dateElement,
  };
  let created = 0;
  const document = {
    querySelector(selector) { return elements[selector] || null; },
    createElement() { created += 1; return fakeElement(); },
    addEventListener() {},
    removeEventListener() {},
  };
  const scheduled = [];
  const scheduler = {
    setTimeout(callback, delay) { scheduled.push({ callback, delay }); return scheduled.length; },
    clearTimeout() {},
  };
  const storage = memoryStorage({
    [preferences.DASHBOARD_SETTINGS_KEY]: JSON.stringify({ speedUnit: "kmh" }),
  });
  const window = {
    navigator: { language: "en-GB" },
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {},
  };
  const now = () => new Date(2026, 6, 16, 7, 5, 30, 250);
  const controller = clock.createController({
    document,
    window,
    preferences,
    storage,
    scheduler,
    now,
    locale: "en-GB",
  });

  assert.equal(controller.start(), true);
  assert.equal(controller.getSnapshot().element, clockElement);
  assert.equal(created, 0);
  assert.equal(valueElement.textContent, "07:05");
  assert.equal(dateElement.hidden, true);
  assert.equal(scheduled[0].delay, 29750);

  assert.equal(controller.setPreference("showDate", true), true);
  assert.equal(dateElement.hidden, false);
  const saved = preferences.readDashboardSettings({}, storage);
  assert.equal(saved.speedUnit, "kmh");
  assert.equal(saved.showDate, true);
});
