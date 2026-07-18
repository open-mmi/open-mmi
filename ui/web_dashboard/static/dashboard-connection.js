(function openMmiDashboardConnectionModule(root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiDashboardConnection = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createDashboardConnectionModule(root) {
  "use strict";

  const HEALTH_PATH = "/api/health";
  const DEFAULT_RETRY_DELAYS_MS = Object.freeze([1000, 2000, 5000, 10000, 15000]);
  const LIVE_CONTROL_SELECTOR = [
    '[data-openmmi-requires-dashboard="true"]',
    "#ommiMediaPlay",
    "#ommiMediaPrev",
    "#ommiMediaNext",
    "#ommiMediaStop",
    "#ommiMediaSearchBtn",
    "#ommiMediaFilter",
    "[data-open-mmi-track]",
  ].join(", ");

  function normaliseDelays(value) {
    const input = Array.isArray(value) ? value : DEFAULT_RETRY_DELAYS_MS;
    const delays = input
      .map((entry) => Number(entry))
      .filter((entry) => Number.isFinite(entry) && entry >= 0);
    return delays.length ? delays : Array.from(DEFAULT_RETRY_DELAYS_MS);
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || windowRef?.document || null;
    const api = options.api || windowRef?.openMmiApi;
    const scheduler = options.scheduler || windowRef || globalThis;
    const retryDelays = normaliseDelays(
      options.retryDelaysMs || windowRef?.__openMmiDashboardRetryDelaysMs,
    );
    const notice = options.notice || documentRef?.querySelector?.("#openMmiDashboardConnectionNotice");
    const noticeMessage = notice?.querySelector?.("[data-openmmi-dashboard-connection-message]");
    let unsubscribeApi = null;
    let retryTimer = null;
    let retryIndex = 0;
    let probeInFlight = false;
    let started = false;
    let state = "connecting";
    let lastError = "";
    let lastConnectedAt = null;
    let lastDisconnectedAt = null;
    const metrics = {
      probes: 0,
      probe_failures: 0,
      recoveries: 0,
      state_changes: 0,
      retry_schedules: 0,
    };

    if (!api || typeof api.getJson !== "function" || typeof api.subscribeConnection !== "function") {
      throw new TypeError("Dashboard connection recovery requires the shared API client");
    }

    function snapshot() {
      return Object.freeze({
        state,
        lastError,
        lastConnectedAt,
        lastDisconnectedAt,
        retryAttempt: retryIndex,
        retryScheduled: retryTimer !== null,
        probeInFlight,
        metrics: Object.freeze({ ...metrics }),
      });
    }

    function dispatch(name, detail) {
      const EventCtor = windowRef?.CustomEvent || root?.CustomEvent;
      if (windowRef?.dispatchEvent && EventCtor) {
        windowRef.dispatchEvent(new EventCtor(name, { detail }));
      }
    }

    function setNotice() {
      if (!notice) return;
      if (state === "ready") {
        notice.hidden = true;
        return;
      }
      const messages = {
        connecting: "Connecting to dashboard…",
        reconnecting: "Dashboard reconnecting… Live controls are paused.",
        unavailable: "Dashboard unavailable. Retrying automatically…",
      };
      if (noticeMessage) noticeMessage.textContent = messages[state] || messages.reconnecting;
      notice.hidden = false;
    }

    function syncLiveControls() {
      const connected = state === "ready";
      documentRef?.querySelectorAll?.(LIVE_CONTROL_SELECTOR)?.forEach?.((control) => {
        if (!connected) {
          if ("disabled" in control && !control.disabled) {
            control.disabled = true;
            control.dataset.openmmiConnectionDisabled = "true";
          }
          if (control.getAttribute?.("aria-disabled") !== "true") {
            control.setAttribute?.("aria-disabled", "true");
            control.dataset.openmmiConnectionAriaDisabled = "true";
          }
          return;
        }
        if (control.dataset?.openmmiConnectionDisabled === "true") {
          control.disabled = false;
          delete control.dataset.openmmiConnectionDisabled;
        }
        if (control.dataset?.openmmiConnectionAriaDisabled === "true") {
          control.removeAttribute?.("aria-disabled");
          delete control.dataset.openmmiConnectionAriaDisabled;
        }
      });
    }

    function emit(previousState) {
      const detail = snapshot();
      if (documentRef?.body?.dataset) documentRef.body.dataset.openmmiDashboardConnection = state;
      setNotice();
      syncLiveControls();
      dispatch("openmmi:dashboardconnection", detail);
      if (state === "ready" && previousState !== "ready") {
        dispatch("openmmi:dashboardconnected", detail);
      }
      if (state !== "ready" && previousState === "ready") {
        dispatch("openmmi:dashboarddisconnected", detail);
      }
      return detail;
    }

    function transition(nextState, error = "") {
      const next = String(nextState || "reconnecting");
      const previous = state;
      state = next;
      lastError = String(error || "");
      if (previous !== next) metrics.state_changes += 1;
      if (next === "ready") {
        const recovered = previous === "reconnecting" || previous === "unavailable";
        if (recovered) metrics.recoveries += 1;
        lastConnectedAt = Date.now();
        retryIndex = 0;
        clearRetry();
      } else if (previous === "ready" || lastDisconnectedAt === null) {
        lastDisconnectedAt = Date.now();
      }
      return emit(previous);
    }

    function clearRetry() {
      if (retryTimer !== null) scheduler?.clearTimeout?.(retryTimer);
      retryTimer = null;
    }

    function hidden() {
      return documentRef?.hidden === true || documentRef?.visibilityState === "hidden";
    }

    function scheduleRetry() {
      clearRetry();
      if (!started || hidden() || state === "ready") return false;
      const index = Math.min(retryIndex, retryDelays.length - 1);
      const delay = retryDelays[index];
      retryIndex += 1;
      metrics.retry_schedules += 1;
      retryTimer = scheduler?.setTimeout?.(probeNow, delay) ?? null;
      if (retryIndex >= retryDelays.length && state !== "unavailable") transition("unavailable", lastError);
      return retryTimer !== null;
    }

    function markReachable() {
      if (state === "ready") return snapshot();
      return transition("ready");
    }

    function markUnreachable(error) {
      const message = String(error?.message || error || "dashboard unavailable");
      if (state === "ready" || state === "connecting") transition("reconnecting", message);
      else lastError = message;
      if (retryTimer === null) scheduleRetry();
      return snapshot();
    }

    function onApiConnection(detail = {}) {
      if (detail.reachable === true) markReachable();
      else if (detail.reachable === false) markUnreachable(detail.error || detail.message);
    }

    async function probeNow() {
      clearRetry();
      if (!started || hidden() || probeInFlight) return snapshot();
      probeInFlight = true;
      metrics.probes += 1;
      try {
        await api.getJson(HEALTH_PATH, { requireOk: false, allowInvalidJson: true });
        if (state !== "ready") markReachable();
      } catch (error) {
        metrics.probe_failures += 1;
        if (state === "ready" || state === "connecting") markUnreachable(error);
      } finally {
        probeInFlight = false;
        if (state !== "ready" && retryTimer === null) scheduleRetry();
      }
      return snapshot();
    }

    function onVisibilityChange() {
      if (hidden()) {
        clearRetry();
        return;
      }
      void probeNow();
    }

    function start() {
      if (started) return false;
      started = true;
      unsubscribeApi = api.subscribeConnection(onApiConnection);
      documentRef?.addEventListener?.("visibilitychange", onVisibilityChange);
      windowRef?.addEventListener?.("online", probeNow);
      windowRef?.addEventListener?.("openmmi:settingsrender", syncLiveControls);
      windowRef?.addEventListener?.("openmmi:pagechange", syncLiveControls);
      emit("");
      void probeNow();
      return true;
    }

    function stop() {
      if (!started) return false;
      started = false;
      clearRetry();
      unsubscribeApi?.();
      unsubscribeApi = null;
      documentRef?.removeEventListener?.("visibilitychange", onVisibilityChange);
      windowRef?.removeEventListener?.("online", probeNow);
      windowRef?.removeEventListener?.("openmmi:settingsrender", syncLiveControls);
      windowRef?.removeEventListener?.("openmmi:pagechange", syncLiveControls);
      return true;
    }

    return Object.freeze({
      markReachable,
      markUnreachable,
      probeNow,
      snapshot,
      start,
      stop,
      syncLiveControls,
    });
  }

  return Object.freeze({
    DEFAULT_RETRY_DELAYS_MS,
    HEALTH_PATH,
    LIVE_CONTROL_SELECTOR,
    createController,
    normaliseDelays,
  });
});
