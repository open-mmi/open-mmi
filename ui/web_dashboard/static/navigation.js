(function openMmiNavigationModule(root, factory) {
  const navigation = factory(root);
  if (typeof module === "object" && module.exports) module.exports = navigation;
  if (root) root.openMmiNavigation = navigation;
})(typeof globalThis !== "undefined" ? globalThis : this, function createOpenMmiNavigation(root) {
  "use strict";

  const QUICK_PAGES = Object.freeze([
    Object.freeze({ id: "pageElectrical", title: "Media", label: "Media" }),
    Object.freeze({ id: "pageHome", title: "Home", label: "Home" }),
    Object.freeze({ id: "pageDrive", title: "Drive", label: "Drive" }),
  ]);
  const MENU_PAGES = Object.freeze({
    climate: Object.freeze({ id: "pageClimate", title: "Climate" }),
    vehicle: Object.freeze({ id: "pageVehicle", title: "Vehicle" }),
  });
  const HOME_INDEX = 1;

  function normaliseIndex(index, length = QUICK_PAGES.length, fallback = HOME_INDEX) {
    const size = Number(length);
    if (!Number.isInteger(size) || size <= 0) return 0;
    const value = Number(index);
    const selected = Number.isFinite(value) ? Math.trunc(value) : fallback;
    return ((selected % size) + size) % size;
  }

  function isEditableTarget(target) {
    return !!(
      target
      && typeof target.closest === "function"
      && target.closest("input, textarea, select, [contenteditable='true'], [contenteditable='']")
    );
  }

  function createController(options = {}) {
    const documentRef = options.document || (root && root.document);
    const windowRef = options.window || root;
    if (!documentRef || typeof documentRef.querySelector !== "function" || typeof documentRef.querySelectorAll !== "function") {
      throw new TypeError("Navigation requires a DOM document");
    }

    const state = {
      activeIndex: HOME_INDEX,
      activePageId: QUICK_PAGES[HOME_INDEX].id,
      initialized: false,
    };
    let keyHandler = null;

    const one = (selector) => documentRef.querySelector(selector);
    const many = (selector) => Array.from(documentRef.querySelectorAll(selector));

    function dispatchPageChange(detail) {
      if (!windowRef || typeof windowRef.dispatchEvent !== "function") return;
      const EventCtor = windowRef.CustomEvent || (root && root.CustomEvent);
      if (typeof EventCtor === "function") {
        windowRef.dispatchEvent(new EventCtor("openmmi:pagechange", { detail }));
      } else {
        windowRef.dispatchEvent({ type: "openmmi:pagechange", detail });
      }
    }

    function homeFmtNumber(value, digits = 0, fallback = "--") {
      const number = Number(value);
      if (!Number.isFinite(number)) return fallback;
      return number.toFixed(digits);
    }

    function homeKmhToMph(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "--";
      return Math.round(number * 0.621371).toString();
    }

    function homeText(value, fallback = "--") {
      return value === null || value === undefined || value === "" ? fallback : String(value);
    }

    function ensureHomePage() {
      let page = one("#pageHome");
      if (!page) {
        page = documentRef.createElement("section");
        page.id = "pageHome";
        page.className = "page page-home";
        page.setAttribute("aria-label", "Home menu");

        const firstPage = one(".page");
        if (firstPage && firstPage.parentNode) firstPage.parentNode.insertBefore(page, firstPage);
        else {
          const footer = one("footer.status-strip") || one("footer");
          (footer && footer.parentNode ? footer.parentNode : documentRef.body).insertBefore(page, footer || null);
        }
      }

      page.innerHTML = `
        <div class="openmmi-home-shell">
          <section class="openmmi-home-card openmmi-home-hero" aria-label="Open MMI summary">
            <div class="openmmi-home-kicker">Open MMI</div>
            <h2>Home</h2>
            <p class="openmmi-home-copy">Local, read-only vehicle status built from decoded signals.</p>
            <div class="openmmi-home-status-grid" aria-label="Live status summary">
              <div class="openmmi-home-stat">
                <span>Speed</span>
                <strong><b id="homeSpeed">--</b><small>mph</small></strong>
              </div>
              <div class="openmmi-home-stat">
                <span>RPM</span>
                <strong><b id="homeRpm">--</b><small>rpm</small></strong>
              </div>
              <div class="openmmi-home-stat">
                <span>Lights</span>
                <strong id="homeLights">--</strong>
              </div>
              <div class="openmmi-home-stat">
                <span>Range</span>
                <strong><b id="homeRange">--</b><small>mi</small></strong>
              </div>
            </div>
          </section>

          <section class="openmmi-home-card openmmi-home-menu" aria-label="Dashboard menu">
            <div class="openmmi-home-menu-head">
              <span>Quick access</span>
              <small>Media ← Home → Drive</small>
            </div>
            <div class="openmmi-home-actions">
              <button type="button" class="openmmi-home-action openmmi-primary" data-openmmi-page="2">
                <span>Drive</span><small>Speed and tell-tales</small>
              </button>
              <button type="button" class="openmmi-home-action openmmi-primary" data-openmmi-page="0">
                <span>Media</span><small>Local Jellyfin player</small>
              </button>
              <button type="button" class="openmmi-home-action" data-openmmi-menu="climate">
                <span>Climate</span><small>HVAC and outside temperature</small>
              </button>
              <button type="button" class="openmmi-home-action" data-openmmi-menu="vehicle">
                <span>Vehicle</span><small>Doors, reverse and status</small>
              </button>
              <button type="button" class="openmmi-home-action" data-openmmi-settings="true">
                <span>Settings</span><small>Units, display and diagnostics</small>
              </button>
            </div>
          </section>
        </div>
      `;
      return page;
    }

    function rebuildPager() {
      const pager = one(".pager");
      if (!pager) return;
      pager.innerHTML = QUICK_PAGES.map((page, index) => `
        <button type="button" data-page="${index}" aria-label="${page.label}" title="${page.label}"></button>
      `).join("");
      pager.querySelectorAll("button[data-page]").forEach((button) => {
        button.addEventListener("click", () => setPage(Number(button.dataset.page)));
      });
    }

    function setActivePageElement(id) {
      many(".page").forEach((page) => page.classList.toggle("active", page.id === id));
    }

    function setPagerActive(index) {
      many(".pager button").forEach((button, buttonIndex) => {
        button.classList.toggle("active", buttonIndex === index);
      });
    }

    function showPageById(id, title, quickIndex = HOME_INDEX) {
      const index = normaliseIndex(quickIndex);
      setActivePageElement(id);
      setPagerActive(index);
      const titleElement = one("#pageTitle");
      if (titleElement) titleElement.textContent = title;
      state.activeIndex = index;
      state.activePageId = id;
      dispatchPageChange({ id, title, quickIndex: index });
      return Object.freeze({ id, title, quickIndex: index });
    }

    function setPage(index) {
      const selected = normaliseIndex(index);
      const page = QUICK_PAGES[selected] || QUICK_PAGES[HOME_INDEX];
      return showPageById(page.id, page.title, selected);
    }

    function pageIndex(pageId) {
      return QUICK_PAGES.findIndex((page) => page.id === pageId);
    }

    function showPage(pageId, title = null, quickIndex = HOME_INDEX) {
      const index = pageIndex(pageId);
      if (index >= 0) return setPage(index);
      const page = one(`#${pageId}`);
      if (!page) return false;
      const ariaTitle = page.getAttribute("aria-label");
      const resolvedTitle = title
        || (ariaTitle ? ariaTitle.replace(/\s+page$/i, "") : "")
        || pageId.replace(/^page/, "")
        || "Open MMI";
      return showPageById(pageId, resolvedTitle, quickIndex);
    }

    function bindHomeButtons() {
      const page = one("#pageHome");
      if (!page) return;
      page.querySelectorAll("[data-openmmi-page]").forEach((button) => {
        button.addEventListener("click", () => setPage(Number(button.dataset.openmmiPage)));
      });
      page.querySelectorAll("[data-openmmi-menu]").forEach((button) => {
        button.addEventListener("click", () => {
          const target = MENU_PAGES[button.dataset.openmmiMenu];
          if (target) showPageById(target.id, target.title, HOME_INDEX);
        });
      });
    }

    function bindKeyboard() {
      if (!windowRef || typeof windowRef.addEventListener !== "function" || keyHandler) return;
      keyHandler = (event) => {
        if (
          event.defaultPrevented
          || event.altKey
          || event.ctrlKey
          || event.metaKey
          || isEditableTarget(event.target)
        ) return;
        if (event.key === "ArrowRight") {
          setPage(state.activeIndex + 1);
          return;
        }
        if (event.key === "ArrowLeft") {
          setPage(state.activeIndex - 1);
          return;
        }
        if (event.key === "Home" || event.key === "h" || event.key === "H") {
          if (typeof event.preventDefault === "function") event.preventDefault();
          setPage(HOME_INDEX);
        }
      };
      windowRef.addEventListener("keydown", keyHandler);
    }

    function update(payload) {
      const status = payload && payload.state ? payload.state : {};
      const vehicle = status.vehicle || {};
      const engine = status.engine || {};
      const fuel = status.fuel || {};
      const lighting = status.lighting || {};

      const speed = one("#homeSpeed");
      if (speed) speed.textContent = homeKmhToMph(vehicle.speed_kmh);

      const rpm = one("#homeRpm");
      if (rpm) rpm.textContent = homeFmtNumber(engine.speed_rpm, 0);

      const range = one("#homeRange");
      if (range) range.textContent = homeKmhToMph(fuel.range_km);

      const lights = one("#homeLights");
      if (lights) lights.textContent = homeText(lighting.mode).replaceAll("_", " ");
    }

    function init() {
      if (state.initialized) return false;
      ensureHomePage();
      rebuildPager();
      bindHomeButtons();
      bindKeyboard();
      state.initialized = true;
      if (windowRef) windowRef.__openMmiHomeMenuNavigationLoaded = true;
      setPage(HOME_INDEX);
      return true;
    }

    function destroy() {
      if (keyHandler && windowRef && typeof windowRef.removeEventListener === "function") {
        windowRef.removeEventListener("keydown", keyHandler);
      }
      keyHandler = null;
      state.initialized = false;
    }

    function getSnapshot() {
      return Object.freeze({
        activeIndex: state.activeIndex,
        activePageId: state.activePageId,
        initialized: state.initialized,
      });
    }

    return Object.freeze({
      destroy,
      getActiveIndex: () => state.activeIndex,
      getPageIds: () => QUICK_PAGES.map((page) => page.id),
      getPageNames: () => QUICK_PAGES.map((page) => page.title),
      getSnapshot,
      init,
      pageIndex,
      setPage,
      showPage,
      showPageById,
      update,
    });
  }

  return Object.freeze({
    HOME_INDEX,
    MENU_PAGES,
    QUICK_PAGES,
    createController,
    isEditableTarget,
    normaliseIndex,
  });
});
