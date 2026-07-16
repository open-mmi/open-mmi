(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiMediaShell = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  const STORE_KEY = "openmmi.dashboard.settings.v1";
  const SOURCES = Object.freeze([
    Object.freeze({ id: "jellyfin", label: "Jellyfin", note: "Local library", planned: false }),
    Object.freeze({ id: "radio", label: "Internet radio", note: "Radio Browser stations", planned: false }),
    Object.freeze({ id: "usb", label: "USB", note: "read-only local media", planned: false }),
    Object.freeze({ id: "bluetooth", label: "Bluetooth", note: "connected phone playback controls", planned: false }),
  ]);
  const SOURCE_IDS = Object.freeze(SOURCES.map((source) => source.id));
  const DEFAULT_MEDIA = Object.freeze({
    mediaActiveSource: "jellyfin",
    mediaDefaultSource: "jellyfin",
    mediaSources: Object.freeze({
      jellyfin: true,
      radio: false,
      usb: false,
      bluetooth: false,
    }),
  });

  function sourceById(id) {
    return SOURCES.find((source) => source.id === id) || SOURCES[0];
  }

  function normalisePreferences(saved = {}) {
    const value = saved && typeof saved === "object" ? saved : {};
    const mediaSources = Object.assign({}, DEFAULT_MEDIA.mediaSources, value.mediaSources || {});
    const prefs = Object.assign({}, DEFAULT_MEDIA, value, { mediaSources });
    if (!SOURCE_IDS.includes(prefs.mediaDefaultSource)) prefs.mediaDefaultSource = "jellyfin";
    if (!SOURCE_IDS.includes(prefs.mediaActiveSource)) {
      prefs.mediaActiveSource = prefs.mediaDefaultSource || "jellyfin";
    }
    return prefs;
  }

  function isEnabledInPreferences(id, prefs) {
    return prefs?.mediaSources?.[id] === true;
  }

  function firstEnabledSource(prefs) {
    return SOURCES.find((source) => isEnabledInPreferences(source.id, prefs))?.id || "";
  }

  function activeSourceFromPreferences(prefs) {
    const value = normalisePreferences(prefs);
    if (isEnabledInPreferences(value.mediaActiveSource, value)) return value.mediaActiveSource;
    if (isEnabledInPreferences(value.mediaDefaultSource, value)) return value.mediaDefaultSource;
    return firstEnabledSource(value);
  }

  function updateSourceEnabled(prefs, id, enabled) {
    const next = normalisePreferences(prefs);
    if (!SOURCE_IDS.includes(id)) return next;
    next.mediaSources[id] = Boolean(enabled);

    if (!activeSourceFromPreferences(next)) {
      const fallback = enabled ? id : firstEnabledSource(next);
      next.mediaActiveSource = fallback || id;
      next.mediaDefaultSource = fallback || next.mediaDefaultSource || id;
    } else if (!isEnabledInPreferences(next.mediaActiveSource, next)) {
      next.mediaActiveSource = activeSourceFromPreferences(next);
    }

    if (!isEnabledInPreferences(next.mediaDefaultSource, next)) {
      next.mediaDefaultSource = activeSourceFromPreferences(next) || next.mediaDefaultSource;
    }
    return next;
  }

  function updateDefaultSource(prefs, id) {
    const next = normalisePreferences(prefs);
    if (SOURCE_IDS.includes(id) && isEnabledInPreferences(id, next)) next.mediaDefaultSource = id;
    return next;
  }

  function updateActiveSource(prefs, id) {
    const next = normalisePreferences(prefs);
    if (SOURCE_IDS.includes(id) && isEnabledInPreferences(id, next)) next.mediaActiveSource = id;
    return next;
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || windowRef?.document;
    const preferences = options.preferences || windowRef?.openMmiPreferences;
    if (!windowRef || !documentRef || !preferences) {
      throw new Error("Media source controller requires window, document and preferences");
    }
    if (windowRef.__openMmiMediaSourceShellV1Loaded && windowRef.openMmiMediaSources) {
      return windowRef.openMmiMediaSources;
    }
    windowRef.__openMmiMediaSourceShellV1Loaded = true;

    const query = (selector) => documentRef.querySelector(selector);
    const requestFrame = typeof windowRef.requestAnimationFrame === "function"
      ? windowRef.requestAnimationFrame.bind(windowRef)
      : (callback) => windowRef.setTimeout(callback, 0);

    function loadPrefs() {
      let saved = {};
      try { saved = preferences.readObject(STORE_KEY, {}); }
      catch (_) { saved = {}; }
      return normalisePreferences(saved);
    }

    function savePrefs(prefs) {
      try { preferences.writeJson(STORE_KEY, prefs); } catch (_) {}
      windowRef.openMmiDashboardSettings = Object.assign({}, windowRef.openMmiDashboardSettings || {}, prefs);
    }

    function isEnabled(id, prefs = loadPrefs()) {
      return isEnabledInPreferences(id, prefs);
    }

    function activeSourceId(prefs = loadPrefs()) {
      return activeSourceFromPreferences(prefs);
    }

    function setSourceEnabled(id, enabled) {
      const prefs = updateSourceEnabled(loadPrefs(), id, enabled);
      savePrefs(prefs);
      apply();
    }

    function setDefaultSource(id) {
      const current = loadPrefs();
      const prefs = updateDefaultSource(current, id);
      if (prefs.mediaDefaultSource === current.mediaDefaultSource) return;
      savePrefs(prefs);
      apply();
    }

    function setActiveSource(id) {
      const current = loadPrefs();
      const prefs = updateActiveSource(current, id);
      if (prefs.mediaActiveSource === current.mediaActiveSource) return;
      savePrefs(prefs);
      apply();

      if (id === "jellyfin") {
        try { if (typeof windowRef.ommiMediaRefreshStatus === "function") windowRef.ommiMediaRefreshStatus(); } catch (_) {}
        try {
          if (
            typeof windowRef.ommiMediaLoadLibrary === "function"
          ) {
            windowRef.ommiMediaLoadLibrary("");
          }
        } catch (_) {}
      }
    }

    function shouldUseJellyfin() {
      // Historical name retained for compatibility. The real media UI is used
      // for every implemented source, not only Jellyfin.
      const prefs = loadPrefs();
      const active = activeSourceId(prefs);
      return ["jellyfin", "radio", "usb", "bluetooth"].includes(active) && isEnabled(active, prefs);
    }

    function renderSourceBar(mediaRoot = query("#openMmiMediaRoot")) {
      if (!mediaRoot) return;
      mediaRoot.classList.add("openmmi-media-source-shell");
      let bar = mediaRoot.querySelector("#openMmiMediaSourceBar");
      if (!bar) {
        bar = documentRef.createElement("div");
        bar.id = "openMmiMediaSourceBar";
        bar.className = "openmmi-media-source-bar";
        mediaRoot.insertBefore(bar, mediaRoot.firstChild);
      }

      const prefs = loadPrefs();
      const active = activeSourceId(prefs);
      const visibleSources = SOURCES.filter((source) => isEnabled(source.id, prefs));
      mediaRoot.classList.toggle("openmmi-media-no-enabled-sources", visibleSources.length === 0);
      bar.innerHTML = visibleSources.map((source) => {
        const selected = source.id === active;
        const planned = source.planned ? '<span class="openmmi-media-source-planned">planned</span>' : "";
        return `
          <button type="button" class="openmmi-media-source-btn${selected ? " is-selected" : ""}" data-openmmi-media-source="${source.id}" aria-pressed="${selected ? "true" : "false"}" title="Switch media source">
            <span>${source.label}</span>${planned}
          </button>`;
      }).join("");
    }

    function renderPlaceholder() {
      const mediaRoot = query("#openMmiMediaRoot");
      if (!mediaRoot) return;
      renderSourceBar(mediaRoot);
      if (shouldUseJellyfin()) {
        mediaRoot.classList.remove("openmmi-media-source-placeholder-active");
        mediaRoot.querySelector("#openMmiMediaSourcePlaceholder")?.remove();
        return;
      }

      const prefs = loadPrefs();
      const active = activeSourceId(prefs);
      const source = active ? sourceById(active) : null;
      mediaRoot.classList.add("openmmi-media-source-placeholder-active");
      let placeholder = mediaRoot.querySelector("#openMmiMediaSourcePlaceholder");
      if (!placeholder) {
        placeholder = documentRef.createElement("section");
        placeholder.id = "openMmiMediaSourcePlaceholder";
        placeholder.className = "openmmi-media-source-placeholder";
        mediaRoot.appendChild(placeholder);
      }

      if (!source) {
        placeholder.innerHTML = `
          <div class="openmmi-media-source-empty-kicker">Media source</div>
          <h2>No media source enabled</h2>
          <p>Enable Jellyfin, radio, USB or Bluetooth from Settings → Media.</p>`;
        return;
      }

      const disabledJellyfin = source.id === "jellyfin" && !isEnabled("jellyfin", prefs);
      placeholder.innerHTML = `
        <div class="openmmi-media-source-empty-kicker">${source.label}</div>
        <h2>${disabledJellyfin ? "Jellyfin disabled" : `${source.label} source placeholder`}</h2>
        <p>${disabledJellyfin ? "Jellyfin is disabled in Settings → Media. No Jellyfin API calls are made while it is disabled." : `${source.note}. This source is available in the selector shell but has no playback backend yet.`}</p>`;
    }

    function settingsRow(title, note, controls) {
      return `<div class="openmmi-setting-row"><div><strong>${title}</strong><small>${note}</small></div><div class="openmmi-setting-controls">${controls}</div></div>`;
    }

    function sourceToggleRow(source, prefs) {
      const enabled = isEnabled(source.id, prefs);
      const note = source.planned
        ? `${source.note}; can be exposed as a placeholder source.`
        : source.id === "usb"
          ? "Read-only local media roots configured or discovered by the dashboard server."
          : source.id === "bluetooth"
            ? "Controls an already-connected Bluetooth media player through BlueZ; pairing stays in the operating system."
            : "Configured server-side with URL/token environment variables.";
      return settingsRow(
        source.label,
        note,
        `<button type="button" class="openmmi-setting-pill${enabled ? "" : " is-selected"}" data-openmmi-media-source-enable="${source.id}" data-openmmi-media-source-value="off" aria-pressed="${enabled ? "false" : "true"}">off</button>`
          + `<button type="button" class="openmmi-setting-pill${enabled ? " is-selected" : ""}" data-openmmi-media-source-enable="${source.id}" data-openmmi-media-source-value="on" aria-pressed="${enabled ? "true" : "false"}">on</button>`,
      );
    }

    function defaultControls(prefs) {
      return SOURCES.map((source) => {
        const enabled = isEnabled(source.id, prefs);
        const selected = prefs.mediaDefaultSource === source.id;
        return `<button type="button" class="openmmi-setting-pill${selected ? " is-selected" : ""}" data-openmmi-media-default-source="${source.id}" ${enabled ? "" : "disabled"} aria-pressed="${selected ? "true" : "false"}">${source.label}</button>`;
      }).join("");
    }

    function renderSettingsPanel() {
      const active = documentRef.querySelector("[data-openmmi-settings-section].active")?.dataset?.openmmiSettingsSection;
      const panel = query("#openmmiSettingsPanel");
      if (active !== "media" || !panel) return;
      const prefs = loadPrefs();
      const activeId = activeSourceId(prefs);
      const activeLabel = activeId ? sourceById(activeId).label : "None";
      const defaultLabel = sourceById(prefs.mediaDefaultSource).label;
      const signature = JSON.stringify({
        activeId,
        defaultId: prefs.mediaDefaultSource,
        enabled: SOURCE_IDS.map((id) => [id, isEnabled(id, prefs)]),
      });
      const existing = panel.querySelector?.('[data-openmmi-media-settings-panel="true"]');
      if (existing?.dataset?.openMmiMediaSettingsSignature === signature) return;

      panel.innerHTML = `
        <div data-openmmi-media-settings-panel="true">
          <div class="openmmi-settings-panel-head"><span>Media</span><small>sources</small></div>
          <div class="openmmi-settings-metric"><span>Active source</span><strong>${activeLabel}</strong></div>
          <div class="openmmi-settings-metric"><span>Default source</span><strong>${defaultLabel}</strong></div>
          ${settingsRow("Default source", "Used when the Media page opens or the active source is disabled.", defaultControls(prefs))}
          ${SOURCES.map((source) => sourceToggleRow(source, prefs)).join("")}
          ${settingsRow("Token privacy", "Jellyfin credentials stay server-side in a private user configuration file.", '<button type="button" class="openmmi-setting-pill is-selected" disabled>locked</button>')}
          ${settingsRow("Media keys", "Browser/system media controls follow the currently selected source where supported.", '<button type="button" class="openmmi-setting-pill is-selected" disabled>active</button>')}
          <div id="openMmiJellyfinSettingsHost"></div>
        </div>`;
      const rendered = panel.querySelector?.('[data-openmmi-media-settings-panel="true"]');
      if (rendered?.dataset) rendered.dataset.openMmiMediaSettingsSignature = signature;
    }

    function apply() {
      const mediaRoot = query("#openMmiMediaRoot");
      if (mediaRoot) {
        renderSourceBar(mediaRoot);
        if (shouldUseJellyfin()) {
          mediaRoot.classList.remove("openmmi-media-source-placeholder-active");
          mediaRoot.querySelector("#openMmiMediaSourcePlaceholder")?.remove();
        } else {
          renderPlaceholder();
        }
      }
      renderSettingsPanel();
    }

    function clickHandler(event) {
      const sourceButton = event.target.closest?.("[data-openmmi-media-source]");
      if (sourceButton) {
        setActiveSource(sourceButton.dataset.openmmiMediaSource);
        return;
      }
      const enableButton = event.target.closest?.("[data-openmmi-media-source-enable]");
      if (enableButton) {
        setSourceEnabled(
          enableButton.dataset.openmmiMediaSourceEnable,
          enableButton.dataset.openmmiMediaSourceValue === "on",
        );
        return;
      }
      const defaultButton = event.target.closest?.("[data-openmmi-media-default-source]");
      if (defaultButton) {
        setDefaultSource(defaultButton.dataset.openmmiMediaDefaultSource);
        return;
      }
      if (event.target.closest?.('[data-openmmi-settings-section="media"]')) {
        requestFrame(renderSettingsPanel);
      }
    }

    documentRef.addEventListener("click", clickHandler);
    windowRef.addEventListener("openmmi:pagechange", () => requestFrame(apply));
    documentRef.addEventListener("DOMContentLoaded", () => requestFrame(apply));
    const Observer = windowRef.MutationObserver;
    if (typeof Observer === "function") {
      const observer = new Observer(() => {
        const active = documentRef.querySelector("[data-openmmi-settings-section].active")?.dataset?.openmmiSettingsSection;
        const panel = query("#openmmiSettingsPanel");
        if (active === "media" && panel && !panel.querySelector("[data-openmmi-media-settings-panel]")) {
          renderSettingsPanel();
        }
      });
      try { observer.observe(documentRef.body, { childList: true, subtree: true }); } catch (_) {}
    }

    const controller = {
      apply,
      activeSourceId,
      isEnabled,
      loadPrefs,
      renderPlaceholder,
      renderSettingsPanel,
      setActiveSource,
      setDefaultSource,
      setSourceEnabled,
      shouldUseJellyfin,
    };
    windowRef.openMmiMediaSources = controller;
    return controller;
  }

  return {
    DEFAULT_MEDIA,
    SOURCES,
    STORE_KEY,
    activeSourceFromPreferences,
    createController,
    firstEnabledSource,
    isEnabledInPreferences,
    normalisePreferences,
    sourceById,
    updateActiveSource,
    updateDefaultSource,
    updateSourceEnabled,
  };
});
