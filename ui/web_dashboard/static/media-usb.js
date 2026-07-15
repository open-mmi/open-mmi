(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiUsbMediaController = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  function formatUsbDuration(seconds, formatter = null) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "…";
    if (typeof formatter === "function") return formatter(value);
    const total = Math.max(0, Math.round(value));
    const minutes = Math.floor(total / 60);
    const remainder = String(total % 60).padStart(2, "0");
    return `${minutes}:${remainder}`;
  }

  function buildUsbBrowseUrl(directoryId = "", query = "", filter = "browse") {
    return `/api/usb/browse?${new URLSearchParams({
      dir: String(directoryId || ""),
      q: String(query || ""),
      limit: "60",
      filter: filter || "browse",
    })}`;
  }

  function installController(options = {}) {
    const window = options.window || root;
    const document = options.document || window?.document;
    if (!window || !document) throw new Error("USB media controller requires a browser document");

  if (window.__openMmiUsbMediaSourceLoaded) return;
  window.__openMmiUsbMediaSourceLoaded = true;

  const state = {
    directoryId: "",
    parentId: null,
    breadcrumbs: [],
    installed: false,
    durationCache: new Map(),
    durationGeneration: 0,
  };

  function usbFolderIcon() {
    return `<svg class="ommi-music-icon ommi-usb-folder-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M2.75 5.5A2.75 2.75 0 0 1 5.5 2.75h4.1c.73 0 1.43.29 1.94.81l1.19 1.19h5.77a2.75 2.75 0 0 1 2.75 2.75v9A2.75 2.75 0 0 1 18.5 19.25h-13A2.75 2.75 0 0 1 2.75 16.5v-11Z"/></svg>`;
  }

  function adapterApi() {
    return window.openMmiMediaAdapters || null;
  }

  function activeUsb() {
    try {
      return adapterApi()?.activeSourceId?.() === "usb";
    } catch (_) {
      return false;
    }
  }


  function usbDurationText(seconds) {
    const formatter = typeof ommiMediaTime === "function" ? ommiMediaTime : null;
    return formatUsbDuration(seconds, formatter);
  }

  function commitUsbDuration(index, item, seconds, generation = state.durationGeneration) {
    const value = Number(seconds);
    if (!item?.id || !Number.isFinite(value) || value <= 0) return false;
    state.durationCache.set(item.id, value);
    item.duration_seconds = value;
    if (generation !== state.durationGeneration) return true;
    const queueItem = openMmiMedia.queue?.[Number(index)];
    if (!queueItem || queueItem.id !== item.id || queueItem.source !== "usb") return true;
    queueItem.duration_seconds = value;
    const duration = document.querySelector(
      `[data-open-mmi-track="${Number(index)}"] .ommi-track-duration`,
    );
    if (duration) {
      duration.textContent = usbDurationText(value);
      duration.removeAttribute("title");
    }
    if (openMmiMedia.current?.id === item.id && typeof ommiMediaUpdateProgress === "function") {
      ommiMediaUpdateProgress();
    }
    return true;
  }

  function probeUsbDuration(entry, generation) {
    return new Promise((resolve) => {
      if (generation !== state.durationGeneration) {
        resolve();
        return;
      }
      const audio = document.createElement("audio");
      let finished = false;
      let timeout = 0;
      const finish = () => {
        if (finished) return;
        finished = true;
        if (timeout) clearTimeout(timeout);
        audio.removeEventListener("loadedmetadata", accept);
        audio.removeEventListener("durationchange", accept);
        audio.removeEventListener("canplay", accept);
        audio.removeEventListener("error", finish);
        try {
          audio.pause();
          audio.removeAttribute("src");
          audio.load();
        } catch (_) {}
        resolve();
      };
      const accept = () => {
        if (commitUsbDuration(entry.index, entry.item, audio.duration, generation)) finish();
      };
      audio.preload = "metadata";
      audio.addEventListener("loadedmetadata", accept);
      audio.addEventListener("durationchange", accept);
      audio.addEventListener("canplay", accept);
      audio.addEventListener("error", finish, { once: true });
      timeout = window.setTimeout(finish, 8000);
      audio.src = usbAdapter().streamUrl(entry.item);
      audio.load();
    });
  }

  async function hydrateUsbDurations(entries, generation) {
    let cursor = 0;
    const workerCount = Math.min(2, entries.length);
    const workers = Array.from({ length: workerCount }, async () => {
      while (generation === state.durationGeneration && cursor < entries.length) {
        const entry = entries[cursor];
        cursor += 1;
        await probeUsbDuration(entry, generation);
      }
    });
    await Promise.all(workers);
  }


  function syncUsbSourceChrome(sourceId = null) {
    const controls = document.querySelector("#ommiUsbBrowserControls");
    if (!controls) return;
    let selected = String(sourceId || "");
    if (!selected) {
      try {
        selected = String(adapterApi()?.activeSourceId?.() || "");
      } catch (_) {
        selected = "";
      }
    }
    controls.hidden = selected !== "usb";
  }

  function usbAdapter() {
    return {
      id: "usb",
      label: "USB Media",
      defaultFilter: "browse",
      filters: {
        browse: "Folders first",
        az: "A–Z",
        recent: "Recently modified",
      },
      searchPlaceholder: "Search this USB folder…",
      searchLabel: "Search USB media; results update as you type",
      emptyText: "No supported audio files or folders found.",
      loadingText: "Loading USB media…",
      readyText: "Tap a folder to browse or a track to play.",
      statusUrl: "/api/usb/status",
      searchUrl(query, filter) {
        return buildUsbBrowseUrl(state.directoryId, query, filter);
      },
      streamUrl(item) {
        return `/api/usb/stream/${encodeURIComponent(item.id)}`;
      },
    };
  }

  function ensureBrowserControls() {
    const root = document.querySelector("#openMmiMediaRoot");
    const results = root?.querySelector("#ommiMediaResults");
    if (!root || !results) return null;
    let controls = root.querySelector("#ommiUsbBrowserControls");
    if (!controls) {
      controls = document.createElement("nav");
      controls.id = "ommiUsbBrowserControls";
      controls.className = "ommi-usb-browser-controls";
      controls.setAttribute("aria-label", "USB folder navigation");
      controls.innerHTML = `<button type="button" class="btn ommi-usb-up" data-openmmi-usb-up aria-label="Go to parent folder" title="Parent folder">← Up</button><span class="ommi-usb-path" aria-live="polite">USB media roots</span>`;
      results.before(controls);
      controls.querySelector("[data-openmmi-usb-up]")?.addEventListener("click", () => {
        state.directoryId = state.parentId ?? "";
        const input = document.querySelector("#ommiMediaSearch");
        if (input) input.value = "";
        usbLoadLibrary("", openMmiMedia.filter || "browse");
      });
    }
    controls.hidden = !activeUsb();
    return controls;
  }

  function updateBrowserControls(payload = {}) {
    const controls = ensureBrowserControls();
    if (!controls) return;
    state.parentId = payload.parent_id ?? null;
    state.breadcrumbs = Array.isArray(payload.breadcrumbs) ? payload.breadcrumbs : [];
    const up = controls.querySelector("[data-openmmi-usb-up]");
    if (up) {
      up.disabled = payload.parent_id === null || payload.parent_id === undefined;
      up.hidden = up.disabled;
    }
    const path = controls.querySelector(".ommi-usb-path");
    if (path) {
      path.textContent = state.breadcrumbs.length
        ? state.breadcrumbs.map((crumb) => crumb.label).join(" / ")
        : "USB media roots";
    }
  }

  function decorateUsbResults(generation) {
    if (!activeUsb() || !openMmiMedia?.queue) return;
    const unresolved = [];
    openMmiMedia.queue.forEach((item, index) => {
      if (item?.source !== "usb") return;
      const button = document.querySelector(`[data-open-mmi-track="${index}"]`);
      if (!button) return;
      const duration = button.querySelector(".ommi-track-duration");
      if (item.kind === "directory") {
        button.classList.add("ommi-usb-directory");
        button.setAttribute("aria-label", `Open folder ${item.name || "USB folder"}`);
        const art = button.querySelector(".ommi-track-art");
        if (art) art.innerHTML = usbFolderIcon();
        if (duration) {
          duration.textContent = "›";
          duration.classList.add("ommi-usb-folder-chevron");
        }
        return;
      }
      if (item.kind !== "audio" || !duration) return;
      const supplied = Number(item.duration_seconds);
      const cached = Number(state.durationCache.get(item.id));
      if (Number.isFinite(supplied) && supplied > 0) {
        commitUsbDuration(index, item, supplied, generation);
      } else if (Number.isFinite(cached) && cached > 0) {
        commitUsbDuration(index, item, cached, generation);
      } else {
        duration.textContent = "…";
        duration.title = "Reading track duration";
        unresolved.push({ index, item });
      }
    });
    if (unresolved.length) void hydrateUsbDurations(unresolved, generation);
  }

  async function usbLoadLibrary(query = "", filter = openMmiMedia.filter || "browse") {
    ommiMediaPage();
    const api = adapterApi();
    const adapter = api?.adapters?.usb;
    if (!adapter || !activeUsb()) return;
    api.applySourceUi?.(adapter);
    const searchButton = document.querySelector("#ommiMediaSearchBtn");
    if (searchButton) {
      searchButton.title = "Search USB media";
      searchButton.setAttribute("aria-label", "Search USB media");
    }
    ommiMediaInstallFilters();
    const filterSelect = document.querySelector("#ommiMediaFilter");
    if (filterSelect) {
      filterSelect.title = "Choose USB media view";
      filterSelect.setAttribute("aria-label", "USB media view");
    }
    ensureBrowserControls();

    const q = String(query || "").trim();
    const selectedFilter = Object.prototype.hasOwnProperty.call(adapter.filters, filter)
      ? filter
      : adapter.defaultFilter;
    const requestSerial = (Number(openMmiMedia.requestSerial) || 0) + 1;
    openMmiMedia.requestSerial = requestSerial;
    openMmiMedia.lastQuery = q;
    openMmiMedia.filter = selectedFilter;
    ommiMediaUpdateFilters();
    ommiMediaSetMessage(q ? "Searching USB media…" : adapter.loadingText);
    ommiMediaSetLoading(true);
    try {
      const payload = await ommiMediaFetchJson(adapter.searchUrl(q, selectedFilter));
      if (requestSerial !== openMmiMedia.requestSerial) return;
      state.directoryId = String(payload.directory_id || "");
      updateBrowserControls(payload);
      const listTitle = document.querySelector("#ommiMediaListTitle");
      if (listTitle) {
        listTitle.textContent = q
          ? `Search results · ${payload.title || "USB media"}`
          : (payload.title || "USB media");
      }
      if (payload.error) ommiMediaSetMessage(payload.error, "error");
      else if (payload.truncated) ommiMediaSetMessage("Showing the first matching USB items; refine the search for more.");
      else ommiMediaSetMessage(adapter.readyText);
      ommiMediaRenderResults(payload.items || []);
    } catch (error) {
      if (requestSerial !== openMmiMedia.requestSerial) return;
      ommiMediaSetMessage(`Could not load USB media: ${error.message}`, "error");
      ommiMediaRenderResults([]);
    } finally {
      if (requestSerial === openMmiMedia.requestSerial) ommiMediaSetLoading(false);
    }
    if (requestSerial === openMmiMedia.requestSerial) ommiMediaFitViewport();
  }

  function patchMediaFunctions() {
    if (state.installed) return;
    const api = adapterApi();
    if (!api?.adapters) return;
    api.adapters.usb = usbAdapter();

    const originalLoadLibrary = ommiMediaLoadLibrary;
    ommiMediaLoadLibrary = function ommiMediaLoadUsbAware(query = "", filter = openMmiMedia.filter) {
      const usbIsActive = activeUsb();
      syncUsbSourceChrome(usbIsActive ? "usb" : null);
      return usbIsActive
        ? usbLoadLibrary(query, filter || "browse")
        : originalLoadLibrary(query, filter);
    };

    const originalRenderResults = ommiMediaRenderResults;
    ommiMediaRenderResults = function ommiMediaRenderUsbAware(items) {
      syncUsbSourceChrome();
      state.durationGeneration += 1;
      const generation = state.durationGeneration;
      originalRenderResults(items);
      decorateUsbResults(generation);
    };

    const originalPlayIndex = ommiMediaPlayIndex;
    ommiMediaPlayIndex = async function ommiMediaPlayUsbAware(index) {
      const item = openMmiMedia.queue?.[Number(index)];
      if (item?.source === "usb" && item.kind === "directory") {
        state.directoryId = item.id;
        const input = document.querySelector("#ommiMediaSearch");
        if (input) input.value = "";
        return usbLoadLibrary("", openMmiMedia.filter || "browse");
      }
      return originalPlayIndex(index);
    };

    const originalSetNowPlaying = ommiMediaSetNowPlaying;
    ommiMediaSetNowPlaying = function ommiMediaSetUsbNowPlaying(item) {
      originalSetNowPlaying(item);
      if (!item && activeUsb()) {
        const title = document.querySelector("#ommiMediaTitle");
        const subtitle = document.querySelector("#ommiMediaSubtitle");
        if (title) title.textContent = "Select USB music";
        if (subtitle) subtitle.textContent = "Browse a folder and tap a track to play locally";
      }
    };

    const playerAudio = document.querySelector("#ommiMediaAudio");
    if (playerAudio && playerAudio.dataset.openMmiUsbDurationSync !== "1") {
      playerAudio.dataset.openMmiUsbDurationSync = "1";
      playerAudio.addEventListener("loadedmetadata", () => {
        const item = openMmiMedia.current;
        if (item?.source !== "usb" || item.kind !== "audio") return;
        const index = openMmiMedia.queue?.findIndex((candidate) => candidate?.id === item.id) ?? -1;
        commitUsbDuration(index, item, playerAudio.duration, state.durationGeneration);
      });
    }

    state.installed = true;
    ensureBrowserControls();
    try { api.syncActiveSource?.(true); } catch (_) {}
  }

  function install() {
    if (!adapterApi()?.adapters || typeof ommiMediaLoadLibrary !== "function") {
      setTimeout(install, 25);
      return;
    }
    patchMediaFunctions();
  }

  document.addEventListener("click", (event) => {
    const sourceButton = event.target.closest?.("[data-openmmi-media-source]");
    if (!sourceButton) return;
    const sourceId = String(sourceButton.getAttribute("data-openmmi-media-source") || "");
    syncUsbSourceChrome(sourceId);
    if (sourceId !== "usb") return;
    requestAnimationFrame(() => {
      ensureBrowserControls();
      if (activeUsb()) usbLoadLibrary("", "browse");
    });
  });
  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(() => {
    ensureBrowserControls();
    syncUsbSourceChrome();
  }));
  document.addEventListener("DOMContentLoaded", install);
  install();

  window.openMmiUsbMedia = {
    state,
    load: usbLoadLibrary,
  };

  }

  return {
    buildUsbBrowseUrl,
    formatUsbDuration,
    installController,
  };
});
