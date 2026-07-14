(function openMmiPreferencesModule(root, factory) {
  const preferences = factory(root);
  if (typeof module === "object" && module.exports) module.exports = preferences;
  if (root) root.openMmiPreferences = preferences;
})(typeof globalThis !== "undefined" ? globalThis : this, function createOpenMmiPreferences(root) {
  "use strict";

  const DASHBOARD_SETTINGS_KEY = "openmmi.dashboard.settings.v1";

  function activeStorage(storage) {
    if (storage) return storage;
    try {
      return root && root.localStorage ? root.localStorage : null;
    } catch (_) {
      return null;
    }
  }

  function readJson(key, fallback = null, storage = null) {
    const store = activeStorage(storage);
    if (!store) return fallback;
    try {
      const raw = store.getItem(key);
      if (raw === null) return fallback;
      const parsed = JSON.parse(raw);
      return parsed === null || parsed === undefined ? fallback : parsed;
    } catch (_) {
      return fallback;
    }
  }

  function readObject(key, fallback = {}, storage = null) {
    const value = readJson(key, null, storage);
    return value && typeof value === "object" ? value : fallback;
  }

  function writeJson(key, value, storage = null) {
    const store = activeStorage(storage);
    if (!store) return false;
    try {
      store.setItem(key, JSON.stringify(value));
      return true;
    } catch (_) {
      return false;
    }
  }

  function remove(key, storage = null) {
    const store = activeStorage(storage);
    if (!store) return false;
    try {
      store.removeItem(key);
      return true;
    } catch (_) {
      return false;
    }
  }

  function readDashboardSettings(defaults = {}, storage = null) {
    return Object.assign({}, defaults, readObject(DASHBOARD_SETTINGS_KEY, {}, storage));
  }

  function writeDashboardSettings(value, storage = null) {
    return writeJson(DASHBOARD_SETTINGS_KEY, value, storage);
  }

  return Object.freeze({
    DASHBOARD_SETTINGS_KEY,
    readDashboardSettings,
    readJson,
    readObject,
    remove,
    writeDashboardSettings,
    writeJson,
  });
});
