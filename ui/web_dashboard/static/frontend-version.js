(function openMmiFrontendVersionModule(root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiFrontendVersion = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createFrontendVersionModule(root) {
  "use strict";

  const VERSION_PATH = "/api/version";
  const RELOAD_TARGET_KEY = "openmmi.frontend.reload-target.v1";
  const DEFAULT_VISIBLE_INTERVAL_MS = 60000;
  const EDITABLE_SELECTOR = "input, textarea, select, [contenteditable]:not([contenteditable='false'])";

  function loadedFrontendId(documentRef) {
    return String(documentRef?.querySelector?.('meta[name="open-mmi-frontend-id"]')?.content || "").trim();
  }

  function isEditable(element) {
    return Boolean(element?.closest?.(EDITABLE_SELECTOR));
  }

  function isSafeToReload(documentRef) {
    if (!documentRef) return true;
    if (documentRef.querySelector?.('[data-openmmi-dirty="true"]')) return false;
    return !isEditable(documentRef.activeElement);
  }

  function createController(options = {}) {
    const windowRef = options.windowRef || root;
    const documentRef = options.documentRef || windowRef?.document;
    let storage = options.sessionStorage || null;
    if (!storage) {
      try { storage = windowRef?.sessionStorage || null; }
      catch (_) { storage = null; }
    }
    const fetchJson = options.fetchJson || (async () => {
      const response = await windowRef.fetch(VERSION_PATH, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    });
    const scheduler = options.scheduler || windowRef;
    const intervalMs = Number.isFinite(Number(options.intervalMs))
      ? Number(options.intervalMs)
      : DEFAULT_VISIBLE_INTERVAL_MS;
    const loadedId = options.loadedId || loadedFrontendId(documentRef);
    const notice = options.notice || documentRef?.querySelector?.("#openMmiUpdateNotice");
    const message = notice?.querySelector?.("[data-openmmi-update-message]");
    const reloadButton = notice?.querySelector?.("[data-openmmi-update-reload]");
    let timerId = null;
    let stopped = false;
    let checking = false;
    let pendingTarget = "";
    let serverId = "";
    let state = "current";
    let lastError = "";

    function emit() {
      const detail = snapshot();
      const EventCtor = windowRef?.CustomEvent || root?.CustomEvent;
      if (windowRef?.dispatchEvent && EventCtor) {
        windowRef.dispatchEvent(new EventCtor("openmmi:frontendversion", { detail }));
      }
      return detail;
    }

    function setNotice(text, visible = true) {
      if (message) message.textContent = text;
      if (notice) notice.hidden = !visible;
    }

    function attemptedTarget() {
      try { return String(storage?.getItem?.(RELOAD_TARGET_KEY) || ""); }
      catch (_) { return ""; }
    }

    function recordTarget(target) {
      try { storage?.setItem?.(RELOAD_TARGET_KEY, target); }
      catch (_) { /* Session storage is optional. */ }
    }

    function clearAttemptedTarget() {
      try { storage?.removeItem?.(RELOAD_TARGET_KEY); }
      catch (_) { /* Session storage is optional. */ }
    }

    function targetUrl(target) {
      const url = new URL(windowRef.location.href);
      url.searchParams.set("openmmi_frontend", target);
      return url.toString();
    }

    function performReload(target, force = false) {
      if (!target) return false;
      if (!force && !isSafeToReload(documentRef)) {
        pendingTarget = target;
        state = "update-ready";
        setNotice("Dashboard update ready. Finish editing, then reload.");
        emit();
        return false;
      }
      if (attemptedTarget() === target) {
        pendingTarget = target;
        state = "mismatch-after-reload";
        setNotice("Dashboard update did not load. Reload manually or restart Open MMI.");
        emit();
        return false;
      }
      recordTarget(target);
      state = "reloading";
      emit();
      windowRef.location.replace(targetUrl(target));
      return true;
    }

    function reconcile(payload) {
      serverId = String(payload?.frontend_id || "").trim();
      if (!serverId || payload?.reload_supported === false || loadedId === "unknown-dev") {
        state = "unavailable";
        return emit();
      }
      if (serverId === loadedId) {
        pendingTarget = "";
        state = "current";
        lastError = "";
        clearAttemptedTarget();
        setNotice("", false);
        return emit();
      }
      pendingTarget = serverId;
      performReload(serverId);
      return snapshot();
    }

    async function checkNow() {
      if (stopped || checking) return snapshot();
      checking = true;
      try {
        const payload = await fetchJson();
        reconcile(payload);
      } catch (error) {
        lastError = String(error?.message || error || "version check failed");
        state = "reconnecting";
        emit();
      } finally {
        checking = false;
        schedule();
      }
      return snapshot();
    }

    function clearTimer() {
      if (timerId !== null) scheduler?.clearTimeout?.(timerId);
      timerId = null;
    }

    function schedule() {
      clearTimer();
      if (stopped || documentRef?.hidden) return;
      timerId = scheduler?.setTimeout?.(checkNow, intervalMs) ?? null;
    }

    function onVisibilityChange() {
      if (documentRef?.hidden) clearTimer();
      else checkNow();
    }

    function reloadNow() {
      return performReload(pendingTarget, true);
    }

    function start() {
      if (stopped) stopped = false;
      documentRef?.addEventListener?.("visibilitychange", onVisibilityChange);
      windowRef?.addEventListener?.("online", checkNow);
      windowRef?.addEventListener?.("openmmi:dashboardconnected", checkNow);
      reloadButton?.addEventListener?.("click", reloadNow);
      checkNow();
      return true;
    }

    function stop() {
      stopped = true;
      clearTimer();
      documentRef?.removeEventListener?.("visibilitychange", onVisibilityChange);
      windowRef?.removeEventListener?.("online", checkNow);
      windowRef?.removeEventListener?.("openmmi:dashboardconnected", checkNow);
      reloadButton?.removeEventListener?.("click", reloadNow);
    }

    function snapshot() {
      return Object.freeze({ loadedId, serverId, pendingTarget, state, lastError });
    }

    return Object.freeze({ checkNow, reconcile, reloadNow, snapshot, start, stop });
  }

  function autoStart() {
    if (!root?.document || root.__openMmiFrontendVersionController) return;
    const controller = createController();
    root.__openMmiFrontendVersionController = controller;
    controller.start();
  }

  if (root?.document?.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", autoStart, { once: true });
  } else if (root?.queueMicrotask) {
    root.queueMicrotask(autoStart);
  } else {
    root?.setTimeout?.(autoStart, 0);
  }

  return Object.freeze({
    DEFAULT_VISIBLE_INTERVAL_MS,
    RELOAD_TARGET_KEY,
    VERSION_PATH,
    createController,
    isEditable,
    isSafeToReload,
    loadedFrontendId,
  });
});
