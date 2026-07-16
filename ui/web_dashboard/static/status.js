(function openMmiStatusModule(root, factory) {
  const status = factory(root);
  if (typeof module === "object" && module.exports) module.exports = status;
  if (root) root.openMmiStatus = status;
})(typeof globalThis !== "undefined" ? globalThis : this, function createOpenMmiStatus(root) {
  "use strict";

  const DEFAULT_STATUS_PATH = "/api/status";
  const DEFAULT_STATUS_INTERVAL_MS = 200;

  function createStore(initialPayload = null) {
    let payload = initialPayload;
    let error = null;
    let version = initialPayload === null ? 0 : 1;
    const subscribers = new Set();
    const errorSubscribers = new Set();

    function notify(listeners, value) {
      for (const listener of Array.from(listeners)) {
        try {
          listener(value, snapshot());
        } catch (_) {
          // One optional frontend observer must not stop dashboard updates.
        }
      }
    }

    function snapshot() {
      return Object.freeze({ payload, error, version });
    }

    function publish(nextPayload) {
      payload = nextPayload;
      error = null;
      version += 1;
      notify(subscribers, payload);
      return payload;
    }

    function fail(nextError) {
      error = nextError instanceof Error ? nextError : new Error(String(nextError));
      notify(errorSubscribers, error);
      return error;
    }

    function subscribe(listener, options = {}) {
      if (typeof listener !== "function") throw new TypeError("Status subscriber must be a function");
      subscribers.add(listener);
      if (options.emitCurrent && version > 0) listener(payload, snapshot());
      return () => subscribers.delete(listener);
    }

    function subscribeErrors(listener) {
      if (typeof listener !== "function") throw new TypeError("Status error subscriber must be a function");
      errorSubscribers.add(listener);
      return () => errorSubscribers.delete(listener);
    }

    return Object.freeze({
      fail,
      getSnapshot: snapshot,
      publish,
      subscribe,
      subscribeErrors,
    });
  }

  function createPoller(options = {}) {
    const api = options.api;
    if (!api || typeof api.getJson !== "function") {
      throw new TypeError("Status polling requires an API client with getJson()");
    }

    const store = options.store || createStore();
    const scheduler = options.scheduler || root;
    if (!scheduler || typeof scheduler.setInterval !== "function" || typeof scheduler.clearInterval !== "function") {
      throw new TypeError("Status polling requires setInterval() and clearInterval()");
    }

    const path = options.path || DEFAULT_STATUS_PATH;
    const intervalMs = Number.isFinite(Number(options.intervalMs))
      ? Number(options.intervalMs)
      : DEFAULT_STATUS_INTERVAL_MS;
    const onPayload = typeof options.onPayload === "function" ? options.onPayload : null;
    const onError = typeof options.onError === "function" ? options.onError : null;
    let intervalId = null;

    async function fetchStatus() {
      try {
        const nextPayload = await api.getJson(path, { requireOk: false });
        store.publish(nextPayload);
        if (onPayload) onPayload(nextPayload, store.getSnapshot());
        return nextPayload;
      } catch (caught) {
        const error = store.fail(caught);
        if (onError) onError(error, store.getSnapshot());
        return null;
      }
    }

    function start() {
      if (intervalId !== null) return false;
      fetchStatus();
      intervalId = scheduler.setInterval(fetchStatus, intervalMs);
      return true;
    }

    function stop() {
      if (intervalId === null) return false;
      scheduler.clearInterval(intervalId);
      intervalId = null;
      return true;
    }

    function isRunning() {
      return intervalId !== null;
    }

    return Object.freeze({
      fetchStatus,
      isRunning,
      start,
      stop,
      store,
    });
  }

  return Object.freeze({
    DEFAULT_STATUS_INTERVAL_MS,
    DEFAULT_STATUS_PATH,
    createPoller,
    createStore,
  });
});
