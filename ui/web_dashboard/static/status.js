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

    const documentRef = options.document || root?.document || null;
    const path = options.path || DEFAULT_STATUS_PATH;
    const intervalMs = Number.isFinite(Number(options.intervalMs))
      ? Number(options.intervalMs)
      : DEFAULT_STATUS_INTERVAL_MS;
    const onPayload = typeof options.onPayload === "function" ? options.onPayload : null;
    const onError = typeof options.onError === "function" ? options.onError : null;
    let intervalId = null;
    let inFlight = null;
    let requestedRunning = false;
    let visibilityBound = false;
    const metrics = {
      fetches: 0,
      failures: 0,
      overlapping_fetches_skipped: 0,
      visibility_pauses: 0,
      visibility_resumes: 0,
    };

    function isHidden() {
      return documentRef?.hidden === true || documentRef?.visibilityState === "hidden";
    }

    async function fetchStatus() {
      if (inFlight) {
        metrics.overlapping_fetches_skipped += 1;
        return inFlight;
      }
      metrics.fetches += 1;
      inFlight = (async () => {
        try {
          const nextPayload = await api.getJson(path, { requireOk: false });
          store.publish(nextPayload);
          if (onPayload) onPayload(nextPayload, store.getSnapshot());
          return nextPayload;
        } catch (caught) {
          metrics.failures += 1;
          const error = store.fail(caught);
          if (onError) onError(error, store.getSnapshot());
          return null;
        } finally {
          inFlight = null;
        }
      })();
      return inFlight;
    }

    function startInterval() {
      if (intervalId !== null || !requestedRunning || isHidden()) return false;
      intervalId = scheduler.setInterval(fetchStatus, intervalMs);
      return true;
    }

    function stopInterval() {
      if (intervalId === null) return false;
      scheduler.clearInterval(intervalId);
      intervalId = null;
      return true;
    }

    function handleVisibilityChange() {
      if (!requestedRunning) return;
      if (isHidden()) {
        if (stopInterval()) metrics.visibility_pauses += 1;
        return;
      }
      metrics.visibility_resumes += 1;
      fetchStatus();
      startInterval();
    }

    function bindVisibility() {
      if (visibilityBound || typeof documentRef?.addEventListener !== "function") return;
      documentRef.addEventListener("visibilitychange", handleVisibilityChange);
      visibilityBound = true;
    }

    function unbindVisibility() {
      if (!visibilityBound || typeof documentRef?.removeEventListener !== "function") return;
      documentRef.removeEventListener("visibilitychange", handleVisibilityChange);
      visibilityBound = false;
    }

    function start() {
      if (requestedRunning) return false;
      requestedRunning = true;
      bindVisibility();
      if (!isHidden()) {
        fetchStatus();
        startInterval();
      }
      return true;
    }

    function stop() {
      if (!requestedRunning) return false;
      requestedRunning = false;
      stopInterval();
      unbindVisibility();
      return true;
    }

    function isRunning() {
      return requestedRunning;
    }

    function getMetrics() {
      return Object.freeze({ ...metrics, in_flight: Boolean(inFlight), interval_active: intervalId !== null });
    }

    return Object.freeze({
      fetchStatus,
      getMetrics,
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
