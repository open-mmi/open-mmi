(function openMmiClockModule(root, factory) {
  const clock = factory(root);
  if (typeof module === "object" && module.exports) module.exports = clock;
  if (root) root.openMmiClock = clock;
  if (root && root.document) clock.autoStart();
})(typeof globalThis !== "undefined" ? globalThis : this, function createOpenMmiClock(root) {
  "use strict";

  const DEFAULTS = Object.freeze({
    showClock: true,
    clockFormat: "24h",
    showDate: false,
  });

  function normaliseSettings(value = {}) {
    const settings = value && typeof value === "object" ? value : {};
    return Object.freeze({
      showClock: settings.showClock !== false,
      clockFormat: settings.clockFormat === "12h" ? "12h" : "24h",
      showDate: settings.showDate === true,
    });
  }

  function millisecondsUntilNextMinute(value = new Date()) {
    const date = value instanceof Date ? value : new Date(value);
    const elapsed = (date.getSeconds() * 1000) + date.getMilliseconds();
    return Math.max(1, 60000 - elapsed);
  }

  function formatClock(value, settings = DEFAULTS, locale = undefined) {
    const date = value instanceof Date ? value : new Date(value);
    const prefs = normaliseSettings(settings);
    const timeOptions = prefs.clockFormat === "12h"
      ? { hour: "numeric", minute: "2-digit", hour12: true }
      : { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
    return Object.freeze({
      time: new Intl.DateTimeFormat(locale, timeOptions).format(date),
      date: new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
      }).format(date),
    });
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || (windowRef && windowRef.document);
    const preferences = options.preferences
      || (windowRef && windowRef.openMmiPreferences)
      || (root && root.openMmiPreferences);
    const storage = options.storage || null;
    const scheduler = options.scheduler || windowRef || root;
    const now = typeof options.now === "function" ? options.now : () => new Date();
    const locale = options.locale
      || (windowRef && windowRef.navigator && windowRef.navigator.language)
      || undefined;

    let clockElement = null;
    let timeElement = null;
    let valueElement = null;
    let dateElement = null;
    let timer = null;
    let started = false;
    let controlsQueued = false;
    let settings = normaliseSettings(DEFAULTS);

    function readSettings() {
      if (!preferences || typeof preferences.readDashboardSettings !== "function") {
        return normaliseSettings(DEFAULTS);
      }
      return normaliseSettings(preferences.readDashboardSettings(DEFAULTS, storage));
    }

    function readAllSettings() {
      if (!preferences || typeof preferences.readDashboardSettings !== "function") return {};
      return preferences.readDashboardSettings({}, storage);
    }

    function writeSetting(key, value) {
      if (!preferences || typeof preferences.writeDashboardSettings !== "function") return false;
      const next = Object.assign({}, readAllSettings(), { [key]: value });
      return preferences.writeDashboardSettings(next, storage);
    }

    function resolveElements() {
      if (!documentRef || typeof documentRef.querySelector !== "function") return false;
      clockElement = documentRef.querySelector("#openMmiClock");
      timeElement = documentRef.querySelector("#openMmiClockTime");
      valueElement = documentRef.querySelector("#openMmiClockValue");
      dateElement = documentRef.querySelector("#openMmiClockDate");
      return !!(clockElement && timeElement && valueElement && dateElement);
    }

    function render(value = now()) {
      if (!clockElement && !resolveElements()) return false;
      const date = value instanceof Date ? value : new Date(value);
      const formatted = formatClock(date, settings, locale);
      clockElement.hidden = !settings.showClock;
      clockElement.dataset.clockFormat = settings.clockFormat;
      clockElement.dataset.showDate = settings.showDate ? "true" : "false";
      valueElement.textContent = formatted.time;
      dateElement.textContent = formatted.date;
      dateElement.hidden = !settings.showDate;
      timeElement.setAttribute("datetime", date.toISOString());
      timeElement.setAttribute(
        "aria-label",
        `Local time ${formatted.time}${settings.showDate ? `, ${formatted.date}` : ""}`,
      );
      return true;
    }

    function clearTimer() {
      if (timer === null) return;
      if (scheduler && typeof scheduler.clearTimeout === "function") scheduler.clearTimeout(timer);
      timer = null;
    }

    function scheduleNextMinute() {
      clearTimer();
      if (!scheduler || typeof scheduler.setTimeout !== "function") return null;
      timer = scheduler.setTimeout(() => {
        render();
        scheduleNextMinute();
      }, millisecondsUntilNextMinute(now()));
      return timer;
    }

    function refreshSettings() {
      settings = readSettings();
      if (windowRef) {
        windowRef.openMmiDashboardSettings = Object.assign(
          {},
          windowRef.openMmiDashboardSettings || {},
          settings,
        );
      }
      render();
      renderSettingsControls();
      return settings;
    }

    function settingValue(key, rawValue) {
      if (key === "showClock" || key === "showDate") return rawValue === "true";
      if (key === "clockFormat") return rawValue === "12h" ? "12h" : "24h";
      return rawValue;
    }

    function setPreference(key, value) {
      if (!Object.prototype.hasOwnProperty.call(DEFAULTS, key)) return false;
      const normalised = settingValue(key, String(value));
      if (!writeSetting(key, normalised)) return false;
      refreshSettings();
      if (windowRef && typeof windowRef.dispatchEvent === "function") {
        const EventCtor = windowRef.CustomEvent || (root && root.CustomEvent);
        const detail = { key, value: normalised, settings };
        if (typeof EventCtor === "function") {
          windowRef.dispatchEvent(new EventCtor("openmmi:clocksettingschange", { detail }));
        } else {
          windowRef.dispatchEvent({ type: "openmmi:clocksettingschange", detail });
        }
      }
      return true;
    }

    function settingRow(label, note, key, choices) {
      const buttons = choices.map(([text, value]) => (
        `<button type="button" class="openmmi-setting-pill" data-openmmi-clock-setting="${key}" data-openmmi-clock-value="${value}">${text}</button>`
      )).join("");
      return `
        <div class="openmmi-setting-row" data-openmmi-clock-setting-row="${key}">
          <div><strong>${label}</strong><small>${note}</small></div>
          <div class="openmmi-setting-controls">${buttons}</div>
        </div>
      `;
    }

    function controlsHtml() {
      return `
        <div data-openmmi-clock-controls="true">
          ${settingRow("Clock", "Show local tablet time on every dashboard page.", "showClock", [["off", "false"], ["on", "true"]])}
          ${settingRow("Clock format", "Choose 24-hour or 12-hour time.", "clockFormat", [["24-hour", "24h"], ["12-hour", "12h"]])}
          ${settingRow("Clock date", "Optionally show the local date below the time.", "showDate", [["off", "false"], ["on", "true"]])}
        </div>
      `;
    }

    function selectedValue(key) {
      if (key === "showClock") return settings.showClock ? "true" : "false";
      if (key === "showDate") return settings.showDate ? "true" : "false";
      return settings.clockFormat;
    }

    function syncControlSelections(host) {
      if (!host || typeof host.querySelectorAll !== "function") return;
      host.querySelectorAll("[data-openmmi-clock-setting]").forEach((button) => {
        const key = button.dataset.openmmiClockSetting;
        const selected = button.dataset.openmmiClockValue === selectedValue(key);
        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    }

    function displaySettingsActive() {
      return !!(
        documentRef
        && typeof documentRef.querySelector === "function"
        && documentRef.querySelector('[data-openmmi-settings-section="display"].active')
      );
    }

    function renderSettingsControls() {
      if (!displaySettingsActive()) return false;
      const panel = documentRef.querySelector("#openmmiSettingsPanel");
      if (!panel) return false;
      let host = panel.querySelector("[data-openmmi-clock-controls]");
      if (!host) {
        if (typeof panel.insertAdjacentHTML === "function") {
          panel.insertAdjacentHTML("beforeend", controlsHtml());
          host = panel.querySelector("[data-openmmi-clock-controls]");
        } else if ("innerHTML" in panel) {
          panel.innerHTML += controlsHtml();
          host = panel.querySelector?.("[data-openmmi-clock-controls]") || null;
        }
      }
      syncControlSelections(host);
      return !!host;
    }

    function queueSettingsControls() {
      if (controlsQueued) return;
      controlsQueued = true;
      const callback = () => {
        controlsQueued = false;
        renderSettingsControls();
      };
      if (windowRef && typeof windowRef.requestAnimationFrame === "function") {
        windowRef.requestAnimationFrame(callback);
      } else if (scheduler && typeof scheduler.setTimeout === "function") {
        scheduler.setTimeout(callback, 0);
      } else {
        callback();
      }
    }

    function closestSettingButton(target) {
      if (!target || typeof target.closest !== "function") return null;
      return target.closest("[data-openmmi-clock-setting]");
    }

    function onDocumentClick(event) {
      const settingButton = closestSettingButton(event.target);
      if (settingButton) {
        event.preventDefault?.();
        setPreference(
          settingButton.dataset.openmmiClockSetting,
          settingButton.dataset.openmmiClockValue,
        );
        return;
      }
      if (event.target?.closest?.('[data-openmmi-settings-section="display"]')) {
        queueSettingsControls();
      }
    }

    function onDocumentKeydown(event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      const settingButton = closestSettingButton(event.target);
      if (!settingButton) return;
      event.preventDefault?.();
      setPreference(
        settingButton.dataset.openmmiClockSetting,
        settingButton.dataset.openmmiClockValue,
      );
    }

    function onStorage(event) {
      if (!preferences || event?.key !== preferences.DASHBOARD_SETTINGS_KEY) return;
      refreshSettings();
    }

    function start() {
      if (started) return true;
      if (!resolveElements()) return false;
      started = true;
      settings = readSettings();
      documentRef.addEventListener?.("click", onDocumentClick);
      documentRef.addEventListener?.("keydown", onDocumentKeydown);
      windowRef?.addEventListener?.("openmmi:settingsrender", queueSettingsControls);
      windowRef?.addEventListener?.("openmmi:pagechange", queueSettingsControls);
      windowRef?.addEventListener?.("storage", onStorage);
      render();
      scheduleNextMinute();
      queueSettingsControls();
      return true;
    }

    function stop() {
      clearTimer();
      if (!started) return false;
      started = false;
      documentRef?.removeEventListener?.("click", onDocumentClick);
      documentRef?.removeEventListener?.("keydown", onDocumentKeydown);
      windowRef?.removeEventListener?.("openmmi:settingsrender", queueSettingsControls);
      windowRef?.removeEventListener?.("openmmi:pagechange", queueSettingsControls);
      windowRef?.removeEventListener?.("storage", onStorage);
      return true;
    }

    function getSnapshot() {
      return Object.freeze({
        started,
        settings,
        timerActive: timer !== null,
        element: clockElement,
      });
    }

    return Object.freeze({
      getSnapshot,
      refreshSettings,
      render,
      renderSettingsControls,
      setPreference,
      start,
      stop,
    });
  }

  function autoStart() {
    if (!root || !root.document) return null;
    if (root.__openMmiClockController) return root.__openMmiClockController;
    const controller = createController();
    root.__openMmiClockController = controller;
    const start = () => controller.start();
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
      start();
    }
    return controller;
  }

  return Object.freeze({
    DEFAULTS,
    autoStart,
    createController,
    formatClock,
    millisecondsUntilNextMinute,
    normaliseSettings,
  });
});
