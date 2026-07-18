(function openMmiJellyfinReconnectModule(root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiJellyfinReconnect = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createOpenMmiJellyfinReconnect(root) {
  "use strict";

  const DEFAULT_RETRY_DELAYS_MS = Object.freeze([1000, 2000, 5000, 10000, 15000]);
  const DEFAULT_READY_INTERVAL_MS = 7000;
  const READY_STATES = new Set(["ready", "playing", "paused"]);

  function normaliseProviderState(payload = {}) {
    const configured = payload?.configured !== false;
    if (!configured) {
      return Object.freeze({
        state: "configuration-missing",
        retryable: false,
        message: payload?.subtitle || payload?.error || "Jellyfin is not configured.",
        payload,
      });
    }

    const explicit = String(payload?.connection_state || "").trim().toLowerCase();
    const status = String(payload?.status || "").trim().toLowerCase();
    if (explicit === "authentication-error") {
      return Object.freeze({
        state: "authentication-error",
        retryable: false,
        message: payload?.subtitle || payload?.error || "Jellyfin credentials were rejected.",
        payload,
      });
    }
    if (explicit === "configuration-missing") {
      return Object.freeze({
        state: "configuration-missing",
        retryable: false,
        message: payload?.subtitle || payload?.error || "Jellyfin is not configured.",
        payload,
      });
    }
    if (explicit === "reconnecting" || explicit === "unavailable") {
      return Object.freeze({
        state: "reconnecting",
        retryable: payload?.retryable !== false,
        message: payload?.subtitle || payload?.error || "Jellyfin is unavailable.",
        payload,
      });
    }
    if (explicit === "server-error") {
      return Object.freeze({
        state: "server-error",
        retryable: payload?.retryable === true,
        message: payload?.subtitle || payload?.error || "Jellyfin returned an error.",
        payload,
      });
    }
    if (explicit === "ready" || READY_STATES.has(status)) {
      return Object.freeze({
        state: "ready",
        retryable: false,
        message: payload?.subtitle || "Jellyfin is ready.",
        payload,
      });
    }
    if (payload?.error || status === "error") {
      return Object.freeze({
        state: payload?.retryable === false ? "server-error" : "reconnecting",
        retryable: payload?.retryable !== false,
        message: payload?.subtitle || payload?.error || "Jellyfin is unavailable.",
        payload,
      });
    }

    return Object.freeze({
      state: "ready",
      retryable: false,
      message: payload?.subtitle || "Jellyfin is ready.",
      payload,
    });
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || windowRef?.document;
    const scheduler = options.scheduler || windowRef || root;
    const requestStatus = options.requestStatus;
    if (typeof requestStatus !== "function") {
      throw new TypeError("Jellyfin reconnection controller requires requestStatus");
    }
    if (!scheduler || typeof scheduler.setTimeout !== "function" || typeof scheduler.clearTimeout !== "function") {
      throw new TypeError("Jellyfin reconnection controller requires timeout scheduling");
    }

    const retryDelays = Array.isArray(options.retryDelaysMs) && options.retryDelaysMs.length
      ? options.retryDelaysMs.map((value) => Math.max(0, Number(value) || 0))
      : [...DEFAULT_RETRY_DELAYS_MS];
    const readyIntervalMs = Math.max(1000, Number(options.readyIntervalMs) || DEFAULT_READY_INTERVAL_MS);
    const isActive = typeof options.isActive === "function" ? options.isActive : () => true;
    const onStateChange = typeof options.onStateChange === "function" ? options.onStateChange : () => {};
    const onRecovered = typeof options.onRecovered === "function" ? options.onRecovered : () => {};

    const state = {
      status: "idle",
      failures: 0,
      lastPayload: null,
      lastMessage: "",
      retryInMs: null,
      started: false,
      disposed: false,
      inFlight: false,
      generation: 0,
    };
    let timer = null;

    function visibleAndActive() {
      return !state.disposed && !documentRef?.hidden && isActive();
    }

    function clearTimer() {
      if (timer !== null) scheduler.clearTimeout(timer);
      timer = null;
      state.retryInMs = null;
    }

    function publish(status, details = {}) {
      state.status = status;
      if (Object.prototype.hasOwnProperty.call(details, "payload")) state.lastPayload = details.payload;
      if (Object.prototype.hasOwnProperty.call(details, "message")) state.lastMessage = details.message || "";
      state.retryInMs = details.retryInMs ?? null;
      onStateChange(Object.freeze({
        status: state.status,
        failures: state.failures,
        payload: state.lastPayload,
        message: state.lastMessage,
        retryInMs: state.retryInMs,
      }));
    }

    function schedule(delayMs, reason) {
      clearTimer();
      if (!visibleAndActive()) return;
      const delay = Math.max(0, Number(delayMs) || 0);
      state.retryInMs = delay;
      timer = scheduler.setTimeout(() => {
        timer = null;
        state.retryInMs = null;
        void attempt(reason);
      }, delay);
    }

    function scheduleFailure(reason) {
      const index = Math.min(Math.max(0, state.failures - 1), retryDelays.length - 1);
      const delay = retryDelays[index] ?? retryDelays[retryDelays.length - 1] ?? 15000;
      publish(state.status, {
        payload: state.lastPayload,
        message: state.lastMessage,
        retryInMs: delay,
      });
      schedule(delay, reason);
    }

    function applyClassification(classification, previousStatus) {
      state.lastPayload = classification.payload;
      state.lastMessage = classification.message;
      if (classification.state === "ready") {
        const recovered = previousStatus === "reconnecting" || previousStatus === "server-error";
        state.failures = 0;
        publish("ready", classification);
        if (recovered) onRecovered(classification.payload);
        schedule(readyIntervalMs, "ready-poll");
        return classification;
      }

      if (classification.state === "configuration-missing" || classification.state === "authentication-error") {
        state.failures = 0;
        clearTimer();
        publish(classification.state, classification);
        return classification;
      }

      state.failures += 1;
      const disconnectedState = classification.state === "server-error" ? "server-error" : "reconnecting";
      publish(disconnectedState, classification);
      if (classification.retryable) scheduleFailure("retry");
      else clearTimer();
      return classification;
    }

    async function attempt(reason = "manual") {
      if (!visibleAndActive() || state.inFlight) return state.lastPayload;
      clearTimer();
      state.inFlight = true;
      const requestGeneration = ++state.generation;
      const previousStatus = state.status;
      if (previousStatus === "idle") publish("connecting", { message: "Connecting to Jellyfin…" });
      try {
        const payload = await requestStatus(reason);
        if (requestGeneration !== state.generation || state.disposed) return payload;
        applyClassification(normaliseProviderState(payload), previousStatus);
        return payload;
      } catch (error) {
        if (requestGeneration !== state.generation || state.disposed) throw error;
        state.failures += 1;
        state.lastPayload = null;
        state.lastMessage = String(error?.message || error || "Jellyfin is unavailable.");
        publish(previousStatus === "ready" ? "reconnecting" : "reconnecting", {
          message: state.lastMessage,
          payload: null,
        });
        scheduleFailure("network-retry");
        return null;
      } finally {
        state.inFlight = false;
      }
    }

    function start() {
      if (state.started || state.disposed) return false;
      state.started = true;
      if (documentRef?.addEventListener) {
        documentRef.addEventListener("visibilitychange", handleVisibilityChange);
      }
      if (windowRef?.addEventListener) {
        windowRef.addEventListener("online", handleWake);
        windowRef.addEventListener("openmmi:pagechange", handleWake);
        windowRef.addEventListener("openmmi:settingschange", handleWake);
      }
      if (visibleAndActive()) void attempt("start");
      return true;
    }

    function stop() {
      clearTimer();
      state.generation += 1;
      state.started = false;
    }

    function dispose() {
      if (state.disposed) return;
      stop();
      state.disposed = true;
      documentRef?.removeEventListener?.("visibilitychange", handleVisibilityChange);
      windowRef?.removeEventListener?.("online", handleWake);
      windowRef?.removeEventListener?.("openmmi:pagechange", handleWake);
      windowRef?.removeEventListener?.("openmmi:settingschange", handleWake);
    }

    function handleVisibilityChange() {
      if (documentRef?.hidden) {
        clearTimer();
        return;
      }
      if (visibleAndActive()) void attempt("visible");
    }

    function handleWake() {
      if (!visibleAndActive()) {
        clearTimer();
        return;
      }
      void attempt("wake");
    }

    function refreshNow(reason = "manual") {
      if (!state.started) state.started = true;
      return attempt(reason);
    }

    function retryNow() {
      state.failures = 0;
      return refreshNow("explicit-retry");
    }

    function reportPayload(payload) {
      const previousStatus = state.status;
      return applyClassification(normaliseProviderState(payload), previousStatus);
    }

    function reportFailure(error) {
      state.failures += 1;
      state.lastPayload = null;
      state.lastMessage = String(error?.message || error || "Jellyfin is unavailable.");
      publish("reconnecting", { message: state.lastMessage, payload: null });
      scheduleFailure("reported-failure");
    }

    return Object.freeze({
      state,
      start,
      stop,
      dispose,
      refreshNow,
      retryNow,
      reportPayload,
      reportFailure,
    });
  }

  return Object.freeze({
    DEFAULT_RETRY_DELAYS_MS,
    DEFAULT_READY_INTERVAL_MS,
    normaliseProviderState,
    createController,
  });
});
