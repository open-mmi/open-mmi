(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiRadioMedia = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  function browserCountryCode(language = "") {
    try {
      const Locale = root?.Intl?.Locale || (typeof Intl !== "undefined" ? Intl.Locale : null);
      if (Locale) {
        const locale = new Locale(language || "");
        if (locale.region && /^[A-Za-z]{2}$/.test(locale.region)) return locale.region.toUpperCase();
      }
    } catch (_) {}
    const match = String(language || "").match(/[-_]([A-Za-z]{2})$/);
    return match ? match[1].toUpperCase() : "";
  }

  function normaliseRadioFilterPreferences(stored = {}, language = "") {
    const value = stored && typeof stored === "object" ? stored : {};
    const hasStoredCountry = Object.prototype.hasOwnProperty.call(value, "country");
    const storedCountry = String(value.country || "");
    return {
      country: hasStoredCountry
        ? (/^[A-Za-z]{2}$/.test(storedCountry) ? storedCountry.toUpperCase() : "")
        : browserCountryCode(language),
      language: String(value.language || "").slice(0, 64),
    };
  }

  function safeFavoriteStation(item) {
    if (!item || item.source !== "radio" || !item.id) return null;
    return {
      id: String(item.id),
      source: "radio",
      is_live: true,
      name: String(item.name || "Unnamed station"),
      artist: String(item.artist || item.country || "Internet radio"),
      album: String(item.album || "Live station"),
      duration_seconds: null,
      image_url: null,
      codec: item.codec || null,
      bitrate: Number(item.bitrate) || null,
      country: item.country || item.artist || null,
      country_code: item.country_code || null,
      language: item.language || null,
      language_codes: item.language_codes || null,
    };
  }

  function filterRadioFavorites(favorites = {}, query = "", prefs = {}) {
    const q = String(query || "").trim().toLocaleLowerCase();
    const country = String(prefs.country || "").toUpperCase();
    const language = String(prefs.language || "").toLocaleLowerCase();
    return Object.values(favorites || {})
      .filter((item) => {
        if (!item || typeof item !== "object") return false;
        if (country && String(item.country_code || "").toUpperCase() !== country) return false;
        if (language && !String(item.language || "").toLocaleLowerCase().includes(language)) return false;
        if (!q) return true;
        return [item.name, item.artist, item.album, item.language]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase().includes(q));
      })
      .sort((left, right) => String(left.name).localeCompare(String(right.name)));
  }

  function installPrivacy(options = {}) {
    const window = options.window || root;
    const document = options.document || window?.document;
    const openMmiPrefs = options.preferences || window?.openMmiPreferences;
    if (!window || !document || !openMmiPrefs) throw new Error("Radio privacy requires browser preferences");

  if (window.__openMmiRadioPrivacyConsentLoaded) return;
  window.__openMmiRadioPrivacyConsentLoaded = true;

  const SETTINGS_KEY = "openmmi.dashboard.settings.v1";
  const CONSENT_KEY = "openmmi.media.radio.privacy-consent.v1";
  const NOTICE_VERSION = "2026-07-11-v1";
  let pendingEnableButton = null;
  let bypassRadioEnableGate = false;

  function readJson(key, fallback = {}) {
    try {
      const parsed = openMmiPrefs.readJson(key, null);
      return parsed && typeof parsed === "object" ? parsed : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    return openMmiPrefs.writeJson(key, value);
  }

  function hasCurrentConsent() {
    const consent = readJson(CONSENT_KEY, {});
    return consent.notice_version === NOTICE_VERSION && Boolean(consent.accepted_at);
  }

  function saveConsent() {
    return writeJson(CONSENT_KEY, {
      notice_version: NOTICE_VERSION,
      accepted_at: new Date().toISOString(),
    });
  }

  function fallbackSource(mediaSources) {
    if (mediaSources?.jellyfin === true) return "jellyfin";
    return Object.entries(mediaSources || {})
      .find(([id, enabled]) => id !== "radio" && enabled === true)?.[0] || "jellyfin";
  }

  function disableRadioPreference() {
    const prefs = readJson(SETTINGS_KEY, {});
    const mediaSources = {
      jellyfin: true,
      radio: false,
      usb: false,
      bluetooth: false,
      ...(prefs.mediaSources || {}),
    };
    const wasEnabled = mediaSources.radio === true;
    mediaSources.radio = false;
    const fallback = fallbackSource(mediaSources);
    if (prefs.mediaActiveSource === "radio") prefs.mediaActiveSource = fallback;
    if (prefs.mediaDefaultSource === "radio") prefs.mediaDefaultSource = fallback;
    prefs.mediaSources = mediaSources;
    writeJson(SETTINGS_KEY, prefs);
    window.openMmiDashboardSettings = {
      ...(window.openMmiDashboardSettings || {}),
      ...prefs,
    };
    return wasEnabled;
  }

  function syncAfterPreferenceChange() {
    try { window.openMmiMediaSources?.apply?.(); } catch (_) {}
    try { window.openMmiMediaAdapters?.syncActiveSource?.(true); } catch (_) {}
    requestAnimationFrame(ensureSettingsReviewControl);
  }

  function ensureDialog() {
    let overlay = document.querySelector("#openMmiRadioPrivacyOverlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "openMmiRadioPrivacyOverlay";
    overlay.className = "openmmi-radio-privacy-overlay";
    overlay.hidden = true;
    overlay.innerHTML = `
      <section class="openmmi-radio-privacy-dialog" role="dialog" aria-modal="true" aria-labelledby="openMmiRadioPrivacyTitle" aria-describedby="openMmiRadioPrivacySummary">
        <div class="openmmi-radio-privacy-heading">
          <div>
            <p class="openmmi-radio-privacy-kicker">External network service</p>
            <h2 id="openMmiRadioPrivacyTitle">Before enabling Internet Radio</h2>
          </div>
          <button type="button" class="btn openmmi-radio-privacy-close" data-openmmi-radio-privacy-close aria-label="Close privacy notice">×</button>
        </div>

        <p id="openMmiRadioPrivacySummary" class="openmmi-radio-privacy-summary">
          Internet Radio is not a local-only feature. Open MMI contacts the community Radio Browser directory and, when you play a station, that station or its hosting provider. Open MMI proxies those connections through the dashboard server, but this does not make them anonymous.
        </p>

        <h3>What external services may receive</h3>
        <ul>
          <li><strong>Radio Browser directory:</strong> the dashboard server's public IP address, request time, the search text and country/language filters you use, station identifiers, the Open MMI application/version User-Agent, and a station-click notification when playback starts.</li>
          <li><strong>Radio station or streaming host:</strong> the dashboard server's public IP address, request time, the requested stream, connection duration and data transferred, and ordinary HTTP request headers. The operator may infer an approximate location from the public IP address.</li>
          <li><strong>Other providers:</strong> a station may use a CDN, hosting company, analytics service, or redirect to another provider. Their logging, retention, and sharing practices are controlled by them, not by Open MMI.</li>
        </ul>

        <h3>What Open MMI does and does not send</h3>
        <ul>
          <li>Open MMI does <strong>not</strong> send your Jellyfin token, Jellyfin library contents, radio favourites, or a unique Open MMI user identifier to Radio Browser or a station.</li>
          <li>Open MMI does not request GPS location. If available, the browser locale may be used to choose an initial country filter; that selected country filter is then included in directory searches.</li>
          <li>Your acknowledgement, Radio enablement, favourites, and country/language preferences are stored in this browser's local storage. They do not automatically sync to other devices.</li>
          <li>If this dashboard is self-hosted at home, the external services will usually see your household's public IP. If it runs on a remote server, they will usually see that server's public IP.</li>
        </ul>

        <p class="openmmi-radio-privacy-caveat">
          Open MMI cannot promise how long external operators keep logs or how they combine them with other information. Use Internet Radio only if you accept those external connections.
        </p>

        <p id="openMmiRadioPrivacyError" class="openmmi-radio-privacy-error" role="alert" hidden></p>

        <label class="openmmi-radio-privacy-ack" for="openMmiRadioPrivacyAck">
          <input type="checkbox" id="openMmiRadioPrivacyAck">
          <span>I understand this notice and want to enable Internet Radio.</span>
        </label>

        <div class="openmmi-radio-privacy-actions">
          <button type="button" class="btn btn-outline-light" data-openmmi-radio-privacy-cancel>Cancel</button>
          <button type="button" class="btn btn-outline-light openmmi-radio-privacy-forget" data-openmmi-radio-privacy-forget hidden>Disable Radio and forget acknowledgement</button>
          <button type="button" class="btn btn-light" data-openmmi-radio-privacy-accept disabled>Enable Internet Radio</button>
        </div>
      </section>`;
    document.body.appendChild(overlay);

    const checkbox = overlay.querySelector("#openMmiRadioPrivacyAck");
    const accept = overlay.querySelector("[data-openmmi-radio-privacy-accept]");
    checkbox?.addEventListener("change", () => {
      if (accept) accept.disabled = !checkbox.checked;
    });

    overlay.addEventListener("click", (event) => {
      if (
        event.target === overlay
        || event.target.closest?.("[data-openmmi-radio-privacy-close]")
        || event.target.closest?.("[data-openmmi-radio-privacy-cancel]")
      ) {
        closeDialog();
        return;
      }
      if (event.target.closest?.("[data-openmmi-radio-privacy-forget]")) {
        try { openMmiPrefs.remove(CONSENT_KEY); } catch (_) {}
        disableRadioPreference();
        try { window.openMmiMediaAdapters?.stopPlayback?.(true); } catch (_) {}
        closeDialog();
        syncAfterPreferenceChange();
        return;
      }
      if (event.target.closest?.("[data-openmmi-radio-privacy-accept]")) {
        if (!checkbox?.checked) return;
        if (!saveConsent() || !hasCurrentConsent()) {
          const error = overlay.querySelector("#openMmiRadioPrivacyError");
          if (error) {
            error.textContent = "Open MMI could not store the acknowledgement in this browser, so Internet Radio remains disabled.";
            error.hidden = false;
          }
          return;
        }
        const enableButton = pendingEnableButton;
        closeDialog();
        ensureSettingsReviewControl();
        if (enableButton?.isConnected) {
          bypassRadioEnableGate = true;
          try { enableButton.click(); } finally { bypassRadioEnableGate = false; }
        }
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !overlay.hidden) closeDialog();
    });
    return overlay;
  }

  function openDialog(mode = "enable", enableButton = null) {
    const overlay = ensureDialog();
    pendingEnableButton = enableButton;
    const checkbox = overlay.querySelector("#openMmiRadioPrivacyAck");
    const ack = overlay.querySelector(".openmmi-radio-privacy-ack");
    const accept = overlay.querySelector("[data-openmmi-radio-privacy-accept]");
    const forget = overlay.querySelector("[data-openmmi-radio-privacy-forget]");
    const review = mode === "review";
    const error = overlay.querySelector("#openMmiRadioPrivacyError");

    if (error) { error.hidden = true; error.textContent = ""; }
    if (checkbox) checkbox.checked = false;
    if (ack) ack.hidden = review;
    if (accept) {
      accept.hidden = review;
      accept.disabled = true;
    }
    if (forget) forget.hidden = !review || !hasCurrentConsent();
    overlay.hidden = false;
    document.body.classList.add("openmmi-radio-privacy-open");
    requestAnimationFrame(() => {
      (review
        ? overlay.querySelector("[data-openmmi-radio-privacy-close]")
        : checkbox)?.focus?.();
    });
  }

  function closeDialog() {
    const overlay = document.querySelector("#openMmiRadioPrivacyOverlay");
    if (overlay) overlay.hidden = true;
    document.body.classList.remove("openmmi-radio-privacy-open");
    pendingEnableButton = null;
  }

  function interceptRadioEnable(event) {
    if (bypassRadioEnableGate || hasCurrentConsent()) return;
    const enableButton = event.target.closest?.(
      '[data-openmmi-media-source-enable="radio"][data-openmmi-media-source-value="on"]',
    );
    const sourceButton = event.target.closest?.('[data-openmmi-media-source="radio"]');
    const defaultButton = event.target.closest?.('[data-openmmi-media-default-source="radio"]');
    if (!enableButton && !sourceButton && !defaultButton) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openDialog("enable", enableButton);
  }

  function ensureSettingsReviewControl() {
    const enableButton = document.querySelector(
      '[data-openmmi-media-source-enable="radio"][data-openmmi-media-source-value="on"]',
    );
    if (!enableButton) return;
    const controls = enableButton.parentElement;
    if (!controls) return;
    let review = controls.querySelector("[data-openmmi-radio-privacy-review]");
    if (!review) {
      review = document.createElement("button");
      review.type = "button";
      review.className = "btn openmmi-radio-privacy-review";
      review.dataset.openmmiRadioPrivacyReview = "true";
      review.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        openDialog("review");
      });
      controls.appendChild(review);
    }
    review.textContent = hasCurrentConsent() ? "Privacy details" : "Privacy notice required";
    review.title = hasCurrentConsent()
      ? "Review the Internet Radio privacy notice"
      : "Acknowledge the privacy notice before enabling Internet Radio";
  }

  // Fail closed even if browser storage becomes unwritable: source adapters
  // cannot select Radio without a current, readable acknowledgement.
  const mediaSourceApi = window.openMmiMediaSources;
  if (mediaSourceApi?.activeSourceId && !mediaSourceApi.__radioPrivacyWrapped) {
    const originalActiveSourceId = mediaSourceApi.activeSourceId.bind(mediaSourceApi);
    mediaSourceApi.activeSourceId = (...args) => {
      const sourceId = originalActiveSourceId(...args);
      if (sourceId !== "radio" || hasCurrentConsent()) return sourceId;
      const prefs = readJson(SETTINGS_KEY, {});
      return fallbackSource(prefs.mediaSources || {});
    };
    mediaSourceApi.__radioPrivacyWrapped = true;
  }

  // A material notice change deliberately invalidates old consent. Existing
  // Radio enablement is disabled before the source adapters begin making calls.
  const revokedExistingEnablement = !hasCurrentConsent() && disableRadioPreference();

  document.addEventListener("click", interceptRadioEnable, true);
  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(ensureSettingsReviewControl));
  document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(ensureSettingsReviewControl));
  const observer = new MutationObserver(() => requestAnimationFrame(ensureSettingsReviewControl));
  try { observer.observe(document.body, { childList: true, subtree: true }); } catch (_) {}
  requestAnimationFrame(() => {
    ensureSettingsReviewControl();
    if (revokedExistingEnablement) syncAfterPreferenceChange();
  });

  window.openMmiRadioPrivacy = {
    consentKey: CONSENT_KEY,
    noticeVersion: NOTICE_VERSION,
    hasCurrentConsent,
    openNotice: () => openDialog("review"),
  };

  }

  function installController(options = {}) {
    const window = options.window || root;
    const document = options.document || window?.document;
    const navigator = options.navigator || window?.navigator || { language: "" };
    const openMmiPrefs = options.preferences || window?.openMmiPreferences;
    if (!window || !document || !openMmiPrefs) throw new Error("Radio controller requires browser preferences");

  if (window.__openMmiMediaSourceAdaptersRadioLoaded) return;
  window.__openMmiMediaSourceAdaptersRadioLoaded = true;

  const RADIO_FAVORITES_KEY = "openmmi.media.radio.favorites.v1";
  const RADIO_FILTER_PREFS_KEY = "openmmi.media.radio.filters.v1";
  let radioOptionsPromise = null;

  function readStoredJson(key, fallback) {
    try {
      const parsed = openMmiPrefs.readJson(key, null);
      return parsed && typeof parsed === "object" ? parsed : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeStoredJson(key, value) {
    try { openMmiPrefs.writeJson(key, value); } catch (_) {}
  }

  function loadRadioFilterPrefs() {
    return normaliseRadioFilterPreferences(
      readStoredJson(RADIO_FILTER_PREFS_KEY, {}),
      navigator.language || "",
    );
  }

  function saveRadioFilterPrefs(prefs) {
    writeStoredJson(RADIO_FILTER_PREFS_KEY, {
      country: /^[A-Za-z]{2}$/.test(String(prefs.country || ""))
        ? String(prefs.country).toUpperCase()
        : "",
      language: String(prefs.language || "").slice(0, 64),
    });
  }

  function loadRadioFavorites() {
    const stored = readStoredJson(RADIO_FAVORITES_KEY, {});
    return Object.fromEntries(
      Object.entries(stored).filter(([id, item]) => id && item && typeof item === "object"),
    );
  }

  function isRadioFavorite(stationId) {
    return Boolean(stationId && loadRadioFavorites()[String(stationId)]);
  }

  function toggleRadioFavorite(item) {
    const station = safeFavoriteStation(item);
    if (!station) return false;
    const favorites = loadRadioFavorites();
    const id = station.id;
    const adding = !favorites[id];
    if (adding) favorites[id] = station;
    else delete favorites[id];
    writeStoredJson(RADIO_FAVORITES_KEY, favorites);
    return adding;
  }

  function filteredRadioFavorites(query = "") {
    return filterRadioFavorites(loadRadioFavorites(), query, loadRadioFilterPrefs());
  }

  const adapters = {
    jellyfin: {
      id: "jellyfin",
      label: "Jellyfin",
      defaultFilter: "recent",
      filters: {
        recent: "Recent music",
        favorites: "Favourites",
        az: "A–Z",
      },
      searchPlaceholder: "Search music…",
      searchLabel: "Search music; results update as you type",
      emptyText: "No tracks found.",
      loadingText: "Loading music…",
      readyText: "Tap any track to play locally.",
      statusUrl: "/api/jellyfin/status",
      searchUrl(query, filter) {
        return `/api/jellyfin/search?${new URLSearchParams({
          q: query,
          limit: "60",
          filter,
        })}`;
      },
      streamUrl(item) {
        return `/api/jellyfin/stream/${encodeURIComponent(item.id)}`;
      },
    },
    radio: {
      id: "radio",
      label: "Internet Radio",
      defaultFilter: "popular",
      filters: {
        popular: "Popular stations",
        votes: "Top rated",
        recent: "Recently active",
        favorites: "Favourites",
      },
      searchPlaceholder: "Search stations…",
      searchLabel: "Search internet radio stations; results update as you type",
      emptyText: "No stations found.",
      loadingText: "Loading radio stations…",
      readyText: "Tap a station to listen live.",
      statusUrl: "/api/radio/status",
      searchUrl(query, filter) {
        const prefs = loadRadioFilterPrefs();
        return `/api/radio/search?${new URLSearchParams({
          q: query,
          limit: "60",
          filter,
          country: prefs.country,
          language: prefs.language,
        })}`;
      },
      localItems(query, filter) {
        return filter === "favorites" ? filteredRadioFavorites(query) : null;
      },
      streamUrl(item) {
        return `/api/radio/stream/${encodeURIComponent(item.id)}`;
      },
    },
  };

  function activeSourceId() {
    const value = window.openMmiMediaSources?.activeSourceId?.();
    return typeof value === "string" ? value : "jellyfin";
  }

  function activeAdapter() {
    return adapters[activeSourceId()] || null;
  }

  function itemAdapter(item) {
    return adapters[item?.source] || activeAdapter() || adapters.jellyfin;
  }

  function fallbackIcon() {
    if (typeof ommiMediaCleanMusicIcon === "function") return ommiMediaCleanMusicIcon();
    return typeof ommiMediaIcon === "function" ? ommiMediaIcon("volume-up-fill") : "";
  }

  function clearSourcePlaceholder() {
    const root = document.querySelector("#openMmiMediaRoot");
    root?.classList.remove("openmmi-media-source-placeholder-active");
    root?.querySelector("#openMmiMediaSourcePlaceholder")?.remove();
  }

  function radioCountryLabel(code) {
    try {
      return new Intl.DisplayNames([navigator.language || "en"], { type: "region" }).of(code) || code;
    } catch (_) {
      return code;
    }
  }

  function titleCase(value) {
    return String(value || "").replace(/(^|[\s-])([a-z])/g, (_match, prefix, letter) => `${prefix}${letter.toUpperCase()}`);
  }

  function populateRadioSelect(select, items, prefsValue, kind) {
    if (!select) return;
    const previous = String(prefsValue || "");
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = kind === "country" ? "All countries" : "All languages";
    select.appendChild(all);
    const normalized = Array.isArray(items) ? [...items] : [];
    normalized.sort((left, right) => {
      const leftLabel = kind === "country" ? radioCountryLabel(left.code) : titleCase(left.name);
      const rightLabel = kind === "country" ? radioCountryLabel(right.code) : titleCase(right.name);
      return leftLabel.localeCompare(rightLabel);
    });
    normalized.forEach((item) => {
      const value = kind === "country" ? String(item.code || "") : String(item.name || "");
      if (!value) return;
      const option = document.createElement("option");
      option.value = value;
      const label = kind === "country" ? radioCountryLabel(value) : titleCase(value);
      const count = Number(item.station_count) || 0;
      option.textContent = count ? `${label} (${count})` : label;
      select.appendChild(option);
    });
    if (previous && !Array.from(select.options).some((option) => option.value === previous)) {
      const option = document.createElement("option");
      option.value = previous;
      option.textContent = kind === "country" ? radioCountryLabel(previous) : titleCase(previous);
      select.appendChild(option);
    }
    select.value = previous;
  }

  function ensureRadioFacetControls() {
    const root = document.querySelector("#openMmiMediaRoot");
    const filter = root?.querySelector("#ommiMediaFilter");
    if (!root || !filter) return null;
    let facets = root.querySelector("#ommiRadioFacets");
    if (!facets) {
      facets = document.createElement("div");
      facets.id = "ommiRadioFacets";
      facets.className = "ommi-radio-facets";
      facets.innerHTML = `
        <label class="visually-hidden" for="ommiRadioCountry">Station country</label>
        <select id="ommiRadioCountry" class="form-select ommi-radio-facet-select" aria-label="Station country"><option value="">All countries</option></select>
        <label class="visually-hidden" for="ommiRadioLanguage">Station language</label>
        <select id="ommiRadioLanguage" class="form-select ommi-radio-facet-select" aria-label="Station language"><option value="">All languages</option></select>`;
      filter.after(facets);
      facets.addEventListener("change", (event) => {
        if (!event.target.matches("select")) return;
        saveRadioFilterPrefs({
          country: facets.querySelector("#ommiRadioCountry")?.value || "",
          language: facets.querySelector("#ommiRadioLanguage")?.value || "",
        });
        const input = document.querySelector("#ommiMediaSearch");
        const value = input?.value || "";
        if (typeof ommiMediaRunSearchNow === "function") ommiMediaRunSearchNow(value);
        else ommiMediaLoadLibrary(value, openMmiMedia.filter);
      });
    }
    facets.hidden = activeAdapter()?.id !== "radio";
    if (!facets.hidden) loadRadioFilterOptions();
    return facets;
  }

  async function loadRadioFilterOptions() {
    const facets = document.querySelector("#ommiRadioFacets");
    if (!facets) return;
    const prefs = loadRadioFilterPrefs();
    const country = facets.querySelector("#ommiRadioCountry");
    const language = facets.querySelector("#ommiRadioLanguage");
    if (!radioOptionsPromise) {
      radioOptionsPromise = ommiMediaFetchJson("/api/radio/options").catch((error) => {
        radioOptionsPromise = null;
        throw error;
      });
    }
    try {
      const payload = await radioOptionsPromise;
      populateRadioSelect(country, payload.countries, prefs.country, "country");
      populateRadioSelect(language, payload.languages, prefs.language, "language");
    } catch (error) {
      if (country) country.value = prefs.country;
      if (language) language.value = prefs.language;
      ommiMediaSetMessage(`Could not load radio filters: ${error.message}`, "error");
    }
  }

  function radioFavoriteIcon(filled) {
    return filled
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2.7 2.78 5.63 6.22.9-4.5 4.39 1.06 6.2L12 16.9l-5.56 2.92 1.06-6.2L3 9.23l6.22-.9L12 2.7Z" fill="currentColor"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3.9 2.38 4.82.28.56.62.09 5.32.77-3.85 3.75-.45.44.11.62.91 5.3-4.76-2.5-.56-.3-.56.3-4.76 2.5.91-5.3.11-.62-.45-.44-3.85-3.75 5.32-.77.62-.09.28-.56L12 3.9Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';
  }

  function ensureRadioFavoriteButton() {
    const root = document.querySelector("#openMmiMediaRoot");
    const stop = root?.querySelector("#ommiMediaStop");
    if (!root || !stop) return null;
    let button = root.querySelector("#ommiMediaFavoriteBtn");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.id = "ommiMediaFavoriteBtn";
      button.className = "btn ommi-icon-btn ommi-radio-favorite-btn";
      stop.before(button);
    }
    button.hidden = activeAdapter()?.id !== "radio";
    syncRadioFavoriteButton();
    return button;
  }

  function syncRadioFavoriteButton(item = openMmiMedia.current) {
    const button = document.querySelector("#ommiMediaFavoriteBtn");
    if (!button) return;
    const available = activeAdapter()?.id === "radio" && item?.source === "radio";
    const filled = available && isRadioFavorite(item.id);
    button.disabled = !available;
    button.hidden = activeAdapter()?.id !== "radio";
    button.setAttribute("aria-pressed", String(filled));
    button.setAttribute("aria-label", filled ? "Remove station from favourites" : "Add station to favourites");
    button.title = button.getAttribute("aria-label");
    button.innerHTML = radioFavoriteIcon(filled);
  }

  function applySourceUi(adapter = activeAdapter()) {
    if (!adapter) return;
    const root = document.querySelector("#openMmiMediaRoot");
    if (!root) return;
    clearSourcePlaceholder();
    root.classList.remove("openmmi-media-source-jellyfin", "openmmi-media-source-radio", "openmmi-media-source-usb", "openmmi-media-source-bluetooth");
    root.classList.add(`openmmi-media-source-${adapter.id}`);
    root.dataset.openMmiMediaSource = adapter.id;

    const input = root.querySelector("#ommiMediaSearch");
    if (input) {
      input.placeholder = adapter.searchPlaceholder;
      input.setAttribute("aria-label", adapter.searchLabel);
    }
    const search = root.querySelector("#ommiMediaSearchBtn");
    if (search) {
      search.title = adapter.id === "radio" ? "Search stations" : "Search music";
      search.setAttribute("aria-label", search.title);
    }
    const player = root.querySelector(".ommi-player-col");
    const browser = root.querySelector(".ommi-browser-col");
    player?.setAttribute("aria-label", `${adapter.label} player`);
    browser?.setAttribute("aria-label", `${adapter.label} browser`);
    ensureRadioFacetControls();
    ensureRadioFavoriteButton();
  }

  function resetRequestState() {
    if (openMmiMedia.searchTimer) {
      clearTimeout(openMmiMedia.searchTimer);
      openMmiMedia.searchTimer = null;
    }
    if (typeof ommiMediaInvalidateRequest === "function") {
      ommiMediaInvalidateRequest();
    } else {
      openMmiMedia.requestSerial = (Number(openMmiMedia.requestSerial) || 0) + 1;
    }
  }

  function stopPlayback(clearSelection = true) {
    const audio = document.querySelector("#ommiMediaAudio");
    if (audio) {
      audio.pause();
      try { audio.currentTime = 0; } catch (_) {}
      audio.removeAttribute("src");
      try { audio.load(); } catch (_) {}
    }
    if (clearSelection) {
      openMmiMedia.current = null;
      openMmiMedia.index = -1;
      document
        .querySelectorAll(".ommi-track.is-playing")
        .forEach((node) => node.classList.remove("is-playing", "active"));
      ommiMediaSetNowPlaying(null);
    }
    ommiMediaUpdateProgress();
    ommiMediaUpdatePlayState();
  }

  ommiMediaInstallFilters = function ommiMediaInstallSourceFilters() {
    const adapter = activeAdapter();
    if (!adapter) return;
    let select = document.querySelector("#ommiMediaFilter");
    const recent = document.querySelector("#ommiMediaRecentBtn");
    if (!select && recent) {
      select = document.createElement("select");
      select.id = "ommiMediaFilter";
      select.className = "form-select ommi-filter-select";
      recent.replaceWith(select);
    }
    if (!select) return;

    if (select.dataset.openMmiAdapterBound !== "true") {
      const clean = select.cloneNode(false);
      select.replaceWith(clean);
      select = clean;
      select.dataset.openMmiAdapterBound = "true";
      select.addEventListener("change", () => {
        const current = activeAdapter();
        if (!current) return;
        const input = document.querySelector("#ommiMediaSearch");
        if (input) input.value = "";
        openMmiMedia.filter = select.value || current.defaultFilter;
        if (typeof ommiMediaRunSearchNow === "function") ommiMediaRunSearchNow("");
        else ommiMediaLoadLibrary("", openMmiMedia.filter);
      });
    }

    if (select.dataset.openMmiSource !== adapter.id) {
      select.replaceChildren();
      Object.entries(adapter.filters).forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
      });
      select.dataset.openMmiSource = adapter.id;
    }
    if (!Object.prototype.hasOwnProperty.call(adapter.filters, openMmiMedia.filter)) {
      openMmiMedia.filter = adapter.defaultFilter;
    }
    select.value = openMmiMedia.filter;
    select.setAttribute(
      "aria-label",
      adapter.id === "radio" ? "Radio station view" : "Music library view",
    );
    select.title = adapter.id === "radio" ? "Choose station view" : "Choose music library view";
    applySourceUi(adapter);
  };

  ommiMediaUpdateFilters = function ommiMediaUpdateSourceFilters() {
    const adapter = activeAdapter();
    const select = document.querySelector("#ommiMediaFilter");
    if (!adapter || !select) return;
    if (!Object.prototype.hasOwnProperty.call(adapter.filters, openMmiMedia.filter)) {
      openMmiMedia.filter = adapter.defaultFilter;
    }
    if (select.value !== openMmiMedia.filter) select.value = openMmiMedia.filter;
  };

  ommiMediaRenderResults = function ommiMediaRenderSourceResults(items) {
    const adapter = activeAdapter() || adapters.jellyfin;
    const results = document.querySelector("#ommiMediaResults");
    const count = document.querySelector("#ommiMediaCount");
    if (!results) return;
    openMmiMedia.queue = Array.isArray(items)
      ? items
          .filter((item) => item && item.id)
          .map((item) => ({
            ...item,
            source: item.source || adapter.id,
            is_live: item.is_live === true || adapter.id === "radio",
          }))
      : [];
    if (count) count.textContent = String(openMmiMedia.queue.length);
    if (!openMmiMedia.queue.length) {
      results.innerHTML = `<div class="ommi-empty">${ommiMediaEsc(adapter.emptyText)}</div>`;
      return;
    }
    const icon = fallbackIcon();
    results.innerHTML = openMmiMedia.queue.map((item, index) => `
      <button type="button" class="list-group-item list-group-item-action d-grid ommi-track" data-open-mmi-track="${index}" role="listitem" aria-label="Play ${ommiMediaEsc(item.name || "item")}">
        <span class="ommi-track-art">${item.image_url ? `<img src="${ommiMediaEsc(item.image_url)}" alt="">` : icon}</span>
        <span class="ommi-track-copy"><strong>${ommiMediaEsc(item.name || "Untitled")}</strong><small>${ommiMediaEsc([item.artist, item.album].filter(Boolean).join(" · ") || adapter.label)}</small></span>
        <span class="ommi-track-duration${item.is_live ? " ommi-live" : ""}">${item.is_live ? "LIVE" : ommiMediaTime(item.duration_seconds)}</span>
      </button>`).join("");
  };

  ommiMediaSetNowPlaying = function ommiMediaSetSourceNowPlaying(item) {
    const adapter = itemAdapter(item);
    const title = document.querySelector("#ommiMediaTitle");
    const subtitle = document.querySelector("#ommiMediaSubtitle");
    if (!title || !subtitle) return;
    if (!item) {
      title.textContent = adapter.id === "radio" ? "Select a station" : "Select music";
      subtitle.textContent = adapter.id === "radio"
        ? "Tap a station to listen live"
        : "Tap a track to play through this dashboard";
      ommiMediaSetArtwork(null);
      syncRadioFavoriteButton(null);
      return;
    }
    title.textContent = ommiMediaText(item.name, "Untitled");
    subtitle.textContent = [item.artist, item.album].filter(Boolean).join(" · ") || adapter.label;
    ommiMediaSetArtwork(item);
    syncRadioFavoriteButton(item);
  };

  ommiMediaUpdateProgress = function ommiMediaUpdateSourceProgress() {
    const audio = document.querySelector("#ommiMediaAudio");
    const elapsed = document.querySelector("#ommiMediaElapsed");
    const duration = document.querySelector("#ommiMediaDuration");
    const fill = document.querySelector("#ommiMediaProgressFill");
    const track = document.querySelector("#ommiMediaProgressTrack");
    if (!audio || !elapsed || !duration || !fill) return;
    const live = openMmiMedia.current?.is_live === true;
    track?.classList.toggle("is-live", live);
    track?.setAttribute("aria-disabled", String(live));
    if (live) {
      elapsed.textContent = "LIVE";
      duration.textContent = "";
      fill.style.width = audio.paused ? "0%" : "100%";
      track?.setAttribute("aria-valuenow", audio.paused ? "0" : "100");
      return;
    }
    const dur = Number.isFinite(audio.duration) && audio.duration > 0
      ? audio.duration
      : Number(openMmiMedia.current?.duration_seconds || 0);
    const pct = dur > 0 ? Math.max(0, Math.min(100, (audio.currentTime / dur) * 100)) : 0;
    elapsed.textContent = ommiMediaTime(audio.currentTime);
    duration.textContent = ommiMediaTime(dur);
    fill.style.width = `${pct}%`;
    track?.setAttribute("aria-valuenow", String(Math.round(pct)));
  };

  ommiMediaLoadLibrary = async function ommiMediaLoadSource(
    query = "",
    filter = openMmiMedia.filter,
  ) {
    ommiMediaPage();
    const adapter = activeAdapter();
    if (!adapter) {
      window.openMmiMediaSources?.renderPlaceholder?.();
      return;
    }
    clearSourcePlaceholder();
    applySourceUi(adapter);
    ommiMediaInstallFilters();
    const q = String(query || "").trim();
    const selectedFilter = Object.prototype.hasOwnProperty.call(adapter.filters, filter)
      ? filter
      : adapter.defaultFilter;
    const requestSerial = (Number(openMmiMedia.requestSerial) || 0) + 1;
    openMmiMedia.requestSerial = requestSerial;
    openMmiMedia.lastQuery = q;
    openMmiMedia.filter = selectedFilter;
    ommiMediaUpdateFilters();

    const listTitle = document.querySelector("#ommiMediaListTitle");
    if (listTitle) {
      listTitle.textContent = q
        ? `Search results · ${adapter.filters[selectedFilter]}`
        : adapter.filters[selectedFilter];
    }
    const localItems = typeof adapter.localItems === "function"
      ? adapter.localItems(q, selectedFilter)
      : null;
    if (Array.isArray(localItems)) {
      ommiMediaSetLoading(false);
      ommiMediaSetMessage(localItems.length ? "Tap a favourite station to listen live." : "No favourite stations match these filters.");
      ommiMediaRenderResults(localItems);
      ommiMediaFitViewport();
      return;
    }
    ommiMediaSetMessage(q ? "Searching…" : adapter.loadingText);
    ommiMediaSetLoading(true);
    try {
      const payload = await ommiMediaFetchJson(adapter.searchUrl(q, selectedFilter));
      if (requestSerial !== openMmiMedia.requestSerial) return;
      if (payload.error) ommiMediaSetMessage(payload.error, "error");
      else ommiMediaSetMessage(adapter.readyText);
      ommiMediaRenderResults(payload.items || []);
    } catch (err) {
      if (requestSerial !== openMmiMedia.requestSerial) return;
      ommiMediaSetMessage(`Could not load ${adapter.label}: ${err.message}`, "error");
      ommiMediaRenderResults([]);
    } finally {
      if (requestSerial === openMmiMedia.requestSerial) ommiMediaSetLoading(false);
    }
    if (requestSerial === openMmiMedia.requestSerial) ommiMediaFitViewport();
  };

  ommiMediaRefreshStatus = async function ommiMediaRefreshSourceStatus() {
    ommiMediaPage();
    const adapter = activeAdapter();
    if (!adapter) return;
    clearSourcePlaceholder();
    applySourceUi(adapter);
    try {
      const status = await ommiMediaFetchJson(adapter.statusUrl);
      const remote = document.querySelector("#ommiMediaRemoteState");
      if (remote) {
        const label = status?.configured
          ? (status?.state_label || status?.status || "ready")
          : "not configured";
        remote.textContent = String(label).toUpperCase();
        remote.title = status?.subtitle || "";
      }
      if (!status?.configured) {
        ommiMediaSetMessage(status?.subtitle || `${adapter.label} is not configured`, "error");
      }
    } catch (err) {
      const remote = document.querySelector("#ommiMediaRemoteState");
      if (remote) remote.textContent = "ERROR";
      ommiMediaSetMessage(`${adapter.label} status failed: ${err.message}`, "error");
    }
  };

  ommiMediaPlayIndex = async function ommiMediaPlaySourceIndex(index) {
    ommiMediaPage();
    const audio = document.querySelector("#ommiMediaAudio");
    const item = openMmiMedia.queue[Number(index)];
    if (!audio || !item) return;
    const adapter = itemAdapter(item);
    openMmiMedia.index = Number(index);
    openMmiMedia.current = item;
    ommiMediaSetNowPlaying(item);
    ommiMediaSetMessage(item.is_live ? "Connecting to live station…" : "Loading audio…");
    document
      .querySelectorAll(".ommi-track.is-playing")
      .forEach((node) => node.classList.remove("is-playing", "active"));
    document
      .querySelector(`[data-open-mmi-track="${openMmiMedia.index}"]`)
      ?.classList.add("is-playing", "active");
    audio.preload = item.is_live ? "none" : "metadata";
    audio.src = adapter.streamUrl(item);
    audio.load();
    try {
      await audio.play();
      ommiMediaSetMessage(item.is_live ? "Playing live radio." : "Playing locally on this dashboard.");
    } catch (err) {
      ommiMediaSetMessage(`Tap play to start audio: ${err.message}`, "error");
    }
    ommiMediaUpdatePlayState();
    ommiMediaUpdateProgress();
    ommiMediaFitViewport();
  };

  ommiMediaBind = function ommiMediaBindSourcePlayer() {
    if (openMmiMedia.bound) return;
    const root = document.querySelector("#openMmiMediaRoot");
    const audio = document.querySelector("#ommiMediaAudio");
    if (!root || !audio) return;
    if (typeof ommiMediaBindLiveSearch === "function") ommiMediaBindLiveSearch(root);

    root.addEventListener("click", async (event) => {
      if (event.target.closest?.("#ommiMediaFavoriteBtn")) {
        const item = openMmiMedia.current;
        const adding = toggleRadioFavorite(item);
        syncRadioFavoriteButton(item);
        ommiMediaSetMessage(adding ? "Station added to favourites." : "Station removed from favourites.");
        if (openMmiMedia.filter === "favorites") {
          ommiMediaLoadLibrary(openMmiMedia.lastQuery || "", "favorites");
        }
        return;
      }
      const trackButton = event.target.closest?.("[data-open-mmi-track]");
      if (trackButton) {
        event.preventDefault();
        await ommiMediaPlayIndex(trackButton.dataset.openMmiTrack);
        return;
      }
      if (event.target.closest?.("#ommiMediaSearchBtn")) {
        const value = document.querySelector("#ommiMediaSearch")?.value || "";
        if (typeof ommiMediaRunSearchNow === "function") return ommiMediaRunSearchNow(value);
        return ommiMediaLoadLibrary(value);
      }
      if (event.target.closest?.("#ommiMediaPrev")) return ommiMediaPrev();
      if (event.target.closest?.("#ommiMediaNext")) return ommiMediaNext();
      if (event.target.closest?.("#ommiMediaStop")) {
        stopPlayback(true);
        ommiMediaSetMessage("Stopped.");
        return;
      }
      if (event.target.closest?.("#ommiMediaPlay")) {
        if (!openMmiMedia.current && openMmiMedia.queue.length) return ommiMediaPlayIndex(0);
        if (audio.paused) {
          try {
            await audio.play();
            ommiMediaSetMessage(openMmiMedia.current?.is_live ? "Playing live radio." : "Playing locally on this dashboard.");
          } catch (err) {
            ommiMediaSetMessage(`Could not start audio: ${err.message}`, "error");
          }
        } else {
          audio.pause();
        }
        ommiMediaUpdatePlayState();
        ommiMediaUpdateProgress();
        return;
      }
      const progress = event.target.closest?.("#ommiMediaProgressTrack");
      if (
        progress
        && !openMmiMedia.current?.is_live
        && Number.isFinite(audio.duration)
        && audio.duration > 0
      ) {
        const rect = progress.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
        audio.currentTime = ratio * audio.duration;
        ommiMediaUpdateProgress();
      }
    });

    audio.addEventListener("timeupdate", ommiMediaUpdateProgress);
    audio.addEventListener("durationchange", ommiMediaUpdateProgress);
    audio.addEventListener("loadedmetadata", ommiMediaUpdateProgress);
    audio.addEventListener("play", () => {
      ommiMediaUpdatePlayState();
      ommiMediaUpdateProgress();
    });
    audio.addEventListener("pause", () => {
      ommiMediaUpdatePlayState();
      ommiMediaUpdateProgress();
    });
    audio.addEventListener("ended", () => {
      if (openMmiMedia.current?.is_live) {
        ommiMediaSetMessage("Radio stream ended. Select the station again to reconnect.", "error");
        ommiMediaUpdatePlayState();
        return;
      }
      ommiMediaNext();
    });
    audio.addEventListener("error", () => {
      const adapter = itemAdapter(openMmiMedia.current);
      ommiMediaSetMessage(
        adapter.id === "radio"
          ? "Radio stream interrupted. Select the station again to reconnect."
          : "Audio stream failed. Check Jellyfin access and codec support.",
        "error",
      );
    });
    window.addEventListener("resize", ommiMediaFitViewport);
    window.addEventListener("orientationchange", () => setTimeout(ommiMediaFitViewport, 100));
    openMmiMedia.bound = true;
  };

  function syncActiveSource(force = false) {
    const sourceId = activeSourceId();
    const adapter = adapters[sourceId] || null;
    if (!adapter) {
      if (force || openMmiMedia.sourceId !== sourceId) {
        openMmiMedia.sourceId = sourceId;
        resetRequestState();
        stopPlayback(true);
        openMmiMedia.queue = [];
      }
      return;
    }
    if (!force && openMmiMedia.sourceId === adapter.id) {
      applySourceUi(adapter);
      return;
    }
    openMmiMedia.sourceId = adapter.id;
    resetRequestState();
    stopPlayback(true);
    openMmiMedia.queue = [];
    openMmiMedia.filter = adapter.defaultFilter;
    openMmiMedia.lastQuery = "";
    const input = document.querySelector("#ommiMediaSearch");
    if (input) input.value = "";
    applySourceUi(adapter);
    ommiMediaInstallFilters();
    ommiMediaRefreshStatus();
    ommiMediaLoadLibrary("", adapter.defaultFilter);
  }

  document.addEventListener("click", (event) => {
    if (
      event.target.closest?.("[data-openmmi-media-source]")
      || event.target.closest?.("[data-openmmi-media-source-enable]")
      || event.target.closest?.("[data-openmmi-media-default-source]")
    ) {
      requestAnimationFrame(() => syncActiveSource());
    }
  });
  window.addEventListener("openmmi:pagechange", () => {
    requestAnimationFrame(() => syncActiveSource());
  });
  document.addEventListener("DOMContentLoaded", () => {
    requestAnimationFrame(() => syncActiveSource(true));
  });
  requestAnimationFrame(() => syncActiveSource(true));

  window.openMmiMediaAdapters = {
    adapters,
    activeAdapter,
    activeSourceId,
    applySourceUi,
    isRadioFavorite,
    loadRadioFilterPrefs,
    stopPlayback,
    syncActiveSource,
    toggleRadioFavorite,
  };

  }

  return {
    browserCountryCode,
    filterRadioFavorites,
    installController,
    installPrivacy,
    normaliseRadioFilterPreferences,
    safeFavoriteStation,
  };
});
