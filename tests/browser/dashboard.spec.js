"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

const ROOT = path.resolve(__dirname, "../..");
const STATIC = path.join(ROOT, "ui", "web_dashboard", "static");
const SETTINGS_KEY = "openmmi.dashboard.settings.v1";

const CSS_FILES = [
  "styles-core.css",
  "styles-media-layout.css",
  "styles-shell.css",
  "styles-media-sources.css",
  "styles-diagnostics.css",
  "styles-media-final.css",
  "styles-clock.css",
  "styles-system-settings.css",
  "styles-runtime-hardening.css",
];

function indexAssets() {
  const index = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  const scripts = [...index.matchAll(/<script\s+src="\/([^"?]+\.js)"\s*><\/script>/g)].map((match) => match[1]);
  const documentHtml = index
    .replace(/<link\b[^>]*>/g, "")
    .replace(/<script\s+src="[^"]+"\s*><\/script>/g, "")
    .replace(
      "</head>",
      `<style data-openmmi-browser-test>${CSS_FILES.map((name) => fs.readFileSync(path.join(STATIC, name), "utf8")).join("\n")}</style></head>`,
    );
  return { documentHtml, scripts };
}

const ASSETS = indexAssets();

function basePayload(overrides = {}) {
  const payload = {
    updated_at: Date.now() / 1000,
    health: { status: "live", age_seconds: 0.1 },
    state: {
      vehicle: {
        speed_kmh: 64,
        odometer_km: 12345,
        handbrake: false,
        reverse: false,
      },
      engine: { speed_rpm: 2150, coolant_temp_c: 91 },
      electrical: { supply_voltage_v: 13.9, terminal30_voltage_v: 13.9 },
      climate: {
        outside_temp_regulation_c: 12.5,
        outside_temp_unfiltered_c: 12.8,
        blower_load_percent: 42,
        rear_window_heater_requested: false,
        recirculation_active: true,
        compressor_active: true,
      },
      lighting: {
        mode: "Auto",
        lights_on: true,
        left_indicator: false,
        right_indicator: false,
        hazards: false,
        bulb_out: false,
        dimmer_percent: 65,
      },
      doors: {
        front_left: false,
        front_right: false,
        rear_left: false,
        rear_right: false,
        boot: false,
        bonnet: false,
        any_open: false,
      },
      fuel: { range_km: 310, range_km_candidate: 310 },
    },
  };

  if (overrides.health) Object.assign(payload.health, overrides.health);
  if (overrides.state) {
    for (const [section, values] of Object.entries(overrides.state)) {
      payload.state[section] = Object.assign({}, payload.state[section] || {}, values);
    }
  }
  return payload;
}

function captureRuntimeFailures(page) {
  const failures = [];
  page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });
  return failures;
}

async function expectNoRuntimeFailures(failures) {
  expect(failures, failures.join("\n")).toEqual([]);
}

async function loadDashboard(page, options = {}) {
  const payload = options.payload || basePayload();
  const storage = options.storage || {};
  const bluetoothPayload = options.bluetoothPayload || { available: false, players: [] };
  const versionPayload = options.versionPayload || {
    api_version: 1,
    build_id: "__OPEN_MMI_FRONTEND_ID__",
    frontend_id: "__OPEN_MMI_FRONTEND_ID__",
    reload_supported: true,
  };
  const systemPayload = options.systemPayload || {
    local_only: true,
    launcher: {
      default_ui: "web",
      open_at_login: true,
      service_active: true,
      service_enabled: true,
      dashboard_reachable: true,
    },
    jellyfin: {
      configured: false,
      url: "",
      auth_mode: "",
      username: "",
      user_id: "",
      library_id: "",
      password_configured: false,
      token_configured: false,
      insecure_tls: false,
      allow_global: false,
      restart_required: false,
      path: "/home/test/.config/open-mmi/dashboard.env",
    },
  };

  await page.setContent(ASSETS.documentHtml, { waitUntil: "domcontentloaded" });
  await page.evaluate(({ initialPayload, initialStorage, initialBluetoothPayload, initialSystemPayload, initialVersionPayload }) => {
    const values = Object.assign({}, initialStorage);
    const localStorageMock = {
      get length() { return Object.keys(values).length; },
      key(index) { return Object.keys(values)[index] ?? null; },
      getItem(key) { return Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : null; },
      setItem(key, value) { values[String(key)] = String(value); },
      removeItem(key) { delete values[String(key)]; },
      clear() { Object.keys(values).forEach((key) => delete values[key]); },
    };
    Object.defineProperty(window, "localStorage", { configurable: true, value: localStorageMock });
    window.__openMmiBrowserStorage = values;
    window.__openMmiStatusFixture = initialPayload;
    window.__openMmiBluetoothFixture = initialBluetoothPayload;
    window.__openMmiSystemFixture = initialSystemPayload;
    window.__openMmiVersionFixture = initialVersionPayload;

    const json = (body, status = 200) => new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
    window.fetch = async (input, init = {}) => {
      const url = String(input instanceof Request ? input.url : input);
      if (url.includes("/api/version")) return json(window.__openMmiVersionFixture);
      if (url.includes("/api/status")) return json(window.__openMmiStatusFixture);
      if (url.includes("/api/health")) return json({ ok: true });
      if (url.includes("/api/system/settings")) return json(window.__openMmiSystemFixture);
      if (url.includes("/api/system/launcher")) {
        const body = JSON.parse(init.body || "{}");
        Object.assign(window.__openMmiSystemFixture.launcher, body);
        return json({ ok: true, launcher: window.__openMmiSystemFixture.launcher });
      }
      if (url.includes("/api/system/jellyfin/test")) return json({ ok: true, test: { connected: true, server_name: "Test Jellyfin" } });
      if (url.endsWith("/api/system/jellyfin") && init.method === "POST") {
        const body = JSON.parse(init.body || "{}");
        Object.assign(window.__openMmiSystemFixture.jellyfin, {
          configured: true,
          url: body.url,
          auth_mode: body.auth_mode,
          username: body.username,
          password_configured: body.auth_mode === "username",
          token_configured: body.auth_mode === "token",
          restart_required: true,
        });
        return json({ ok: true, jellyfin: window.__openMmiSystemFixture.jellyfin, test: { connected: true } });
      }
      if (url.includes("/api/system/jellyfin/clear")) {
        Object.assign(window.__openMmiSystemFixture.jellyfin, { configured: false, restart_required: true });
        return json({ ok: true, jellyfin: window.__openMmiSystemFixture.jellyfin });
      }
      if (url.includes("/api/system/dashboard/restart")) {
        window.__openMmiSystemFixture.jellyfin.restart_required = false;
        return json({ ok: true, restarting: true });
      }
      if (url.includes("/api/jellyfin/status")) return json({ configured: false, available: false, libraries: [] });
      if (url.includes("/api/jellyfin/")) return json({ configured: false, available: false, items: [] });
      if (url.includes("/api/bluetooth/status")) return json(window.__openMmiBluetoothFixture);
      if (url.includes("/api/bluetooth/control")) return json({ ok: false, error: "Unavailable" }, 409);
      if (url.includes("/api/usb/status")) return json({ available: false, roots: [] });
      if (url.includes("/api/usb/")) return json({ available: false, entries: [] });
      if (url.includes("/api/radio/")) return json({ available: false, stations: [], countries: [], languages: [] });
      return json({ ok: true, method: init.method || "GET" });
    };

    if (window.HTMLMediaElement) {
      window.HTMLMediaElement.prototype.play = function play() {
        Object.defineProperty(this, "paused", { configurable: true, value: false });
        return Promise.resolve();
      };
      window.HTMLMediaElement.prototype.pause = function pause() {
        Object.defineProperty(this, "paused", { configurable: true, value: true });
      };
    }
  }, {
    initialPayload: payload,
    initialStorage: storage,
    initialBluetoothPayload: bluetoothPayload,
    initialSystemPayload: systemPayload,
    initialVersionPayload: versionPayload,
  });

  if (options.focusBeforeReady) {
    await page.evaluate(() => {
      const input = document.createElement("input");
      input.id = "openMmiUnsavedTestInput";
      input.value = "unsaved";
      input.dataset.openmmiDirty = "true";
      document.body.appendChild(input);
      input.focus();
    });
  }
  for (const script of ASSETS.scripts) {
    const content = `${fs.readFileSync(path.join(STATIC, script), "utf8")}
//# sourceURL=${script}`;
    await page.addScriptTag({ content });
  }
  await page.evaluate(() => document.dispatchEvent(new Event("DOMContentLoaded", { bubbles: true })));
  await expect(page.locator("#pageHome")).toHaveClass(/active/);
  return {
    async setPayload(nextPayload) {
      await page.evaluate((next) => { window.__openMmiStatusFixture = next; }, nextPayload);
    },
    async setBluetoothPayload(nextPayload) {
      await page.evaluate((next) => { window.__openMmiBluetoothFixture = next; }, nextPayload);
    },
    async storage() {
      return page.evaluate(() => Object.assign({}, window.__openMmiBrowserStorage));
    },
  };
}

async function openHome(page) {
  await expect(page.locator("#pageHome")).toHaveClass(/active/);
  await expect(page.locator("#pageTitle")).toHaveText("Home");
}

async function openSettings(page) {
  await openHome(page);
  await page.locator('[data-openmmi-settings="true"]').click();
  await expect(page.locator("#pageSettings")).toHaveClass(/active/);
  await expect(page.locator("#pageTitle")).toHaveText("Settings");
}

async function openMedia(page) {
  await openHome(page);
  await page.locator('[data-openmmi-page="0"]').click();
  await expect(page.locator("#pageElectrical")).toHaveClass(/active/);
  await expect(page.locator("#pageTitle")).toHaveText("Media");
  await expect(page.locator("#openMmiMediaRoot")).toBeVisible();
}


test("frontend build mismatch defers reload while an editable field is active", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  await loadDashboard(page, {
    focusBeforeReady: true,
    versionPayload: {
      api_version: 1,
      build_id: "build-b",
      frontend_id: "build-b",
      reload_supported: true,
    },
  });

  await expect(page.locator("#openMmiUpdateNotice")).toBeVisible();
  await expect(page.locator("[data-openmmi-update-message]")).toContainText("Finish editing");
  await expect(page.locator("#openMmiUnsavedTestInput")).toBeFocused();
  await expectNoRuntimeFailures(failures);
});

test("loads, renders status and navigates with buttons and keyboard", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  await loadDashboard(page);
  await openHome(page);

  await expect(page.locator("#healthText")).toHaveText("live");
  await expect(page.locator("#homeSpeed")).not.toHaveText("--");

  await page.locator('[data-openmmi-page="2"]').click();
  await expect(page.locator("#pageDrive")).toHaveClass(/active/);
  await expect(page.locator('[data-field="speed_mph"]').first()).not.toHaveText("--");

  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#pageTitle")).toHaveText("Media");
  await page.keyboard.press("Home");
  await expect(page.locator("#pageTitle")).toHaveText("Home");

  await page.locator('[data-openmmi-menu="climate"]').click();
  await expect(page.locator("#pageClimate")).toHaveClass(/active/);
  await expect(page.locator('[data-bool="recirculation"]')).toHaveText("ON");

  await expectNoRuntimeFailures(failures);
});


test("diagnostics renders canonical profile values and all decoded paths", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  await loadDashboard(page);
  await openSettings(page);
  await page.locator('[data-openmmi-settings-section="diagnostics"]').click();

  const metricValue = (label) => page.locator(".openmmi-settings-metric").filter({ has: page.locator("span", { hasText: label }) }).first().locator("strong");
  await expect(metricValue("Outside display")).toHaveText("12.5 °C");
  await expect(metricValue("Coolant")).toHaveText("91.0 °C");
  await expect(metricValue("Voltage")).toHaveText("13.9 V");
  await expect(metricValue("RPM")).toHaveText("2150 rpm");
  await expect(page.locator(".openmmi-settings-diagnostics-details")).toContainText("engine.speed_rpm");
  await expect(page.locator(".openmmi-settings-diagnostics-details")).toContainText("electrical.supply_voltage_v");
  await expect(page.locator(".openmmi-settings-diagnostics-details")).toContainText("climate.blower_load_percent");

  await expectNoRuntimeFailures(failures);
});

test("diagnostics updates values in place without flashing or rebuilding fields", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  const dashboard = await loadDashboard(page);
  await openSettings(page);
  await page.locator('[data-openmmi-settings-section="diagnostics"]').click();

  const voltage = page.locator('[data-openmmi-diagnostic-key="electrical.voltage"]');
  await expect(voltage).toHaveText("13.9 V");
  await page.evaluate(() => {
    window.__openMmiDiagnosticsVoltageNode = document.querySelector(
      '[data-openmmi-diagnostic-key="electrical.voltage"]',
    );
  });

  await dashboard.setPayload(basePayload({
    state: { electrical: { supply_voltage_v: 14.2, terminal30_voltage_v: 14.2 } },
  }));
  await expect(voltage).toHaveText("14.2 V");
  await page.waitForTimeout(500);

  expect(await page.evaluate(() => (
    window.__openMmiDiagnosticsVoltageNode
      === document.querySelector('[data-openmmi-diagnostic-key="electrical.voltage"]')
  ))).toBe(true);
  await expectNoRuntimeFailures(failures);
});

test("door and reverse overlays dismiss and reactivate on lifecycle changes", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  const dashboard = await loadDashboard(page);

  await dashboard.setPayload(basePayload({ state: { doors: { front_left: true, any_open: true } } }));
  await expect(page.locator("#openMmiVehicleOverlay")).toBeVisible();
  await expect(page.locator("#openMmiVehicleOverlay [data-door-mark=\"front_left\"]")).toHaveClass(/open/);
  await page.locator("#openMmiDoorOverlayDismiss").click();
  await expect(page.locator("#openMmiVehicleOverlay")).toBeHidden();
  await page.waitForTimeout(350);
  await expect(page.locator("#openMmiVehicleOverlay")).toBeHidden();

  await dashboard.setPayload(basePayload({ state: { doors: { front_left: true, rear_left: true, any_open: true } } }));
  await expect(page.locator("#openMmiVehicleOverlay")).toBeVisible();
  await page.locator("#openMmiDoorOverlayDismiss").click();

  await dashboard.setPayload(basePayload({ state: { vehicle: { reverse: true } } }));
  await expect(page.locator("#openMmiReverseOverlay")).toBeVisible();
  await page.locator("#openMmiReverseOverlayDismiss").click();
  await expect(page.locator("#openMmiReverseOverlay")).toBeHidden();
  await page.waitForTimeout(350);
  await expect(page.locator("#openMmiReverseOverlay")).toBeHidden();

  await dashboard.setPayload(basePayload());
  await page.waitForTimeout(250);
  await dashboard.setPayload(basePayload({ state: { vehicle: { reverse: true } } }));
  await expect(page.locator("#openMmiReverseOverlay")).toBeVisible();

  await expectNoRuntimeFailures(failures);
});

test("settings persist units and display mode across page reconstruction", async ({ page, context }) => {
  const failures = captureRuntimeFailures(page);
  const dashboard = await loadDashboard(page);
  await openSettings(page);

  const speedRow = page.locator(".openmmi-setting-row").filter({ hasText: "Speed" });
  await speedRow.getByRole("button", { name: "km/h" }).click();

  await page.locator('[data-openmmi-settings-section="display"]').click();
  const dimRow = page.locator(".openmmi-setting-row").filter({ hasText: "Dim mode" });
  await dimRow.getByRole("button", { name: "on", exact: true }).click();

  const saved = await dashboard.storage();
  const prefs = JSON.parse(saved[SETTINGS_KEY]);
  expect(prefs.speedUnit).toBe("kmh");
  expect(prefs.dimMode).toBe(true);
  await expect(page.locator("html")).toHaveClass(/openmmi-dim-mode/);

  const rebuilt = await context.newPage();
  const rebuiltFailures = captureRuntimeFailures(rebuilt);
  await loadDashboard(rebuilt, { storage: saved });
  await expect(rebuilt.locator("html")).toHaveClass(/openmmi-dim-mode/);
  await rebuilt.locator('[data-openmmi-settings="true"]').click();
  await expect(rebuilt.locator("#pageSettings")).toHaveClass(/active/);
  await expect(rebuilt.locator(".openmmi-setting-row").filter({ hasText: "Speed" }).getByRole("button", { name: "km/h" })).toHaveAttribute("aria-pressed", "true");

  await expectNoRuntimeFailures(failures);
  await expectNoRuntimeFailures(rebuiltFailures);
  await rebuilt.close();
});

test("media source selection persists and hides disabled sources", async ({ page, context }) => {
  const failures = captureRuntimeFailures(page);
  const initialSettings = {
    mediaActiveSource: "jellyfin",
    mediaDefaultSource: "jellyfin",
    mediaSources: { jellyfin: true, radio: false, usb: true, bluetooth: true },
  };
  const dashboard = await loadDashboard(page, {
    storage: { [SETTINGS_KEY]: JSON.stringify(initialSettings) },
  });
  await openMedia(page);

  const usb = page.locator('[data-openmmi-media-source="usb"]');
  await expect(usb).toBeVisible();
  await usb.click();
  await expect(usb).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator('[data-openmmi-media-source="radio"]')).toHaveCount(0);

  const saved = await dashboard.storage();
  expect(JSON.parse(saved[SETTINGS_KEY]).mediaActiveSource).toBe("usb");

  const rebuilt = await context.newPage();
  const rebuiltFailures = captureRuntimeFailures(rebuilt);
  await loadDashboard(rebuilt, { storage: saved });
  await rebuilt.locator('[data-openmmi-page="0"]').click();
  await expect(rebuilt.locator('[data-openmmi-media-source="usb"]')).toHaveAttribute("aria-pressed", "true");

  await expectNoRuntimeFailures(failures);
  await expectNoRuntimeFailures(rebuiltFailures);
  await rebuilt.close();
});

test("Bluetooth transport follows steering-wheel status changes", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  const initialSettings = {
    mediaActiveSource: "bluetooth",
    mediaDefaultSource: "bluetooth",
    mediaSources: { jellyfin: true, radio: true, usb: true, bluetooth: true },
  };
  const playing = {
    available: true,
    configured: true,
    status: "playing",
    state_label: "playing",
    player_id: "player-1",
    playback_status: "playing",
    position_seconds: 12,
    duration_seconds: 120,
    track: { id: "track-1", name: "Test track", title: "Test track", artist: "Artist" },
    controls: { play_pause: true, play: true, pause: true, stop: true, previous: true, next: true },
  };
  const dashboard = await loadDashboard(page, {
    storage: { [SETTINGS_KEY]: JSON.stringify(initialSettings) },
    bluetoothPayload: playing,
  });
  await openMedia(page);

  const playButton = page.locator("#ommiMediaPlay");
  await expect(playButton).toHaveAttribute("aria-label", /Pause Bluetooth playback/);

  // Simulate a prior dashboard-issued optimistic state, then a genuine BlueZ
  // transition caused by the steering wheel or connected phone.
  await page.evaluate(() => {
    window.openMmiBluetoothMedia.state.playbackOverride = "playing";
    window.openMmiBluetoothMedia.state.lastServerPlaybackStatus = "playing";
  });
  await dashboard.setBluetoothPayload({
    ...playing,
    status: "paused",
    state_label: "paused",
    playback_status: "paused",
    position_seconds: 12.2,
  });
  await page.evaluate(() => window.openMmiBluetoothMedia.refresh());

  await expect(playButton).toHaveAttribute("aria-label", /Play Bluetooth media/);
  await expectNoRuntimeFailures(failures);
});

test("Diagnostics remains scrollable while live values refresh", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  const payload = basePayload();
  payload.state.profile_debug = Object.fromEntries(
    Array.from({ length: 80 }, (_, index) => [`signal_${String(index).padStart(2, "0")}`, index]),
  );
  const dashboard = await loadDashboard(page, { payload });
  await openSettings(page);
  await page.locator('[data-openmmi-settings-section="diagnostics"]').click();

  const scroller = page.locator("#pageSettings .openmmi-settings-panel-card");
  await expect(scroller.locator("summary")).toContainText("Decoded profile values");
  await scroller.evaluate((element) => { element.scrollTop = Math.max(1, element.scrollHeight - element.clientHeight - 40); });
  const before = await scroller.evaluate((element) => element.scrollTop);
  expect(before).toBeGreaterThan(0);

  await scroller.dispatchEvent("pointerdown");
  for (let index = 0; index < 4; index += 1) {
    const next = basePayload({ state: { engine: { speed_rpm: 2200 + index } } });
    next.state.profile_debug = payload.state.profile_debug;
    await dashboard.setPayload(next);
    await page.waitForTimeout(120);
  }
  const during = await scroller.evaluate((element) => element.scrollTop);
  expect(during).toBeGreaterThanOrEqual(before - 2);

  await page.waitForTimeout(500);
  const after = await scroller.evaluate((element) => element.scrollTop);
  expect(after).toBeGreaterThanOrEqual(before - 2);
  await expectNoRuntimeFailures(failures);
});

test("switching away from Bluetooth releases shared transport controls", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  const initialSettings = {
    mediaActiveSource: "bluetooth",
    mediaDefaultSource: "bluetooth",
    mediaSources: { jellyfin: true, radio: true, usb: true, bluetooth: true },
  };
  await loadDashboard(page, {
    storage: { [SETTINGS_KEY]: JSON.stringify(initialSettings) },
  });
  await openMedia(page);

  const transportButtons = [
    page.locator("#ommiMediaPlay"),
    page.locator("#ommiMediaPrev"),
    page.locator("#ommiMediaNext"),
    page.locator("#ommiMediaStop"),
  ];
  await expect(transportButtons[0]).toBeDisabled();

  await page.locator('[data-openmmi-media-source="usb"]').click();
  for (const button of transportButtons) await expect(button).toBeEnabled();

  await expectNoRuntimeFailures(failures);
});

for (const viewport of [
  { name: "vehicle display", width: 800, height: 480 },
  { name: "narrow portrait", width: 390, height: 844 },
]) {
  test(`keeps critical UI within the viewport on ${viewport.name}`, async ({ page }) => {
    const failures = captureRuntimeFailures(page);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await loadDashboard(page);

    const metrics = await page.evaluate(() => {
      const rect = (selector) => {
        const value = document.querySelector(selector)?.getBoundingClientRect();
        return value ? { width: value.width, height: value.height, left: value.left, right: value.right } : null;
      };
      return {
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        topbar: rect(".topbar"),
        footer: rect("footer.status-strip"),
        activePage: rect(".page.active"),
      };
    });

    expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    expect(metrics.bodyWidth).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    expect(metrics.topbar.width).toBeGreaterThan(0);
    expect(metrics.footer.width).toBeGreaterThan(0);
    expect(metrics.activePage.width).toBeGreaterThan(0);
    expect(metrics.topbar.left).toBeGreaterThanOrEqual(-1);
    expect(metrics.footer.right).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    await expect(page.locator("#pageTitle")).toBeVisible();
    await expect(page.locator(".pager")).toBeVisible();

    await expectNoRuntimeFailures(failures);
  });
}
test("Bluetooth button follows a synthetic remote pause promptly", async ({ page }) => {
  const failures = captureRuntimeFailures(page);

  const initialSettings = {
    mediaActiveSource: "bluetooth",
    mediaDefaultSource: "bluetooth",
    mediaSources: {
      jellyfin: true,
      radio: true,
      usb: true,
      bluetooth: true,
    },
  };

  await loadDashboard(page, {
    storage: {
      [SETTINGS_KEY]: JSON.stringify(initialSettings),
    },
  });

  await page.evaluate(() => {
    window.__syntheticBluetoothPlaybackStatus = "playing";

    const originalFetch = window.fetch;

    window.fetch = async (input, init = {}) => {
      const url = String(input instanceof Request ? input.url : input);

      if (url.includes("/api/bluetooth/status")) {
        return new Response(
          JSON.stringify({
            configured: true,
            available: true,
            status: "ready",
            state_label: "connected",
            subtitle: "Synthetic Bluetooth player",
            playback_status: window.__syntheticBluetoothPlaybackStatus,
            player_id: "synthetic-player",
            device_name: "Synthetic phone",
            player_name: "Synthetic Bluetooth",
            position_seconds: 20,
            duration_seconds: 180,
            controls: {
              play_pause: true,
              previous: true,
              next: true,
              stop: true,
            },
            track: {
              id: "synthetic-track",
              title: "Synthetic track",
              artist: "Open MMI",
            },
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        );
      }

      return originalFetch(input, init);
    };
  });

  await openMedia(page);

  await page.evaluate(() => window.openMmiBluetoothMedia.refresh());

  const playButton = page.locator("#ommiMediaPlay");

  await expect(playButton).toHaveAttribute(
    "aria-label",
    /pause bluetooth playback/i,
    { timeout: 2500 },
  );

  await page.evaluate(() => {
    window.__syntheticBluetoothPlaybackStatus = "paused";
  });

  await page.evaluate(() => window.openMmiBluetoothMedia.refresh());

  await expect(playButton).toHaveAttribute(
    "aria-label",
    /play bluetooth media/i,
    { timeout: 2500 },
  );

  await expectNoRuntimeFailures(failures);
});
test("shared clock persists display preferences and survives page navigation", async ({ page, context }) => {
  const failures = captureRuntimeFailures(page);
  const dashboard = await loadDashboard(page);

  const clock = page.locator("#openMmiClock");
  await expect(clock).toBeVisible();
  await expect(page.locator("#openMmiClockValue")).toHaveText(/^\d{2}:\d{2}$/);
  await expect(clock).toHaveAttribute("data-clock-format", "24h");
  await expect(clock).toHaveAttribute("data-show-date", "false");

  await page.evaluate(() => { window.__openMmiClockElementIdentity = document.querySelector("#openMmiClock"); });
  await page.locator('[data-openmmi-page="2"]').click();
  await expect(page.locator("#pageDrive")).toHaveClass(/active/);
  await page.locator('.pager button[data-page="0"]').click();
  await expect(page.locator("#pageElectrical")).toHaveClass(/active/);
  expect(await page.evaluate(() => window.__openMmiClockElementIdentity === document.querySelector("#openMmiClock"))).toBe(true);

  await page.keyboard.press("Home");
  await openSettings(page);
  await page.locator('[data-openmmi-settings-section="display"]').click();

  const formatRow = page.locator('[data-openmmi-clock-setting-row="clockFormat"]');
  const dateRow = page.locator('[data-openmmi-clock-setting-row="showDate"]');
  const visibilityRow = page.locator('[data-openmmi-clock-setting-row="showClock"]');
  await expect(formatRow).toBeVisible();
  await formatRow.getByRole("button", { name: "12-hour" }).click();
  await dateRow.getByRole("button", { name: "on", exact: true }).click();

  await expect(clock).toHaveAttribute("data-clock-format", "12h");
  await expect(clock).toHaveAttribute("data-show-date", "true");
  await expect(page.locator("#openMmiClockValue")).toHaveText(/^\d{1,2}:\d{2}\s(?:am|pm)$/i);
  await expect(page.locator("#openMmiClockDate")).toBeVisible();

  await visibilityRow.getByRole("button", { name: "off", exact: true }).click();
  await expect(clock).toBeHidden();
  await visibilityRow.getByRole("button", { name: "on", exact: true }).click();
  await expect(clock).toBeVisible();

  const saved = await dashboard.storage();
  const prefs = JSON.parse(saved[SETTINGS_KEY]);
  expect(prefs.clockFormat).toBe("12h");
  expect(prefs.showDate).toBe(true);
  expect(prefs.showClock).toBe(true);

  const rebuilt = await context.newPage();
  const rebuiltFailures = captureRuntimeFailures(rebuilt);
  await loadDashboard(rebuilt, { storage: saved });
  await expect(rebuilt.locator("#openMmiClock")).toHaveAttribute("data-clock-format", "12h");
  await expect(rebuilt.locator("#openMmiClockDate")).toBeVisible();

  await expectNoRuntimeFailures(failures);
  await expectNoRuntimeFailures(rebuiltFailures);
  await rebuilt.close();
});


test("system settings and Jellyfin setup use the shared local configuration API", async ({ page }) => {
  const failures = captureRuntimeFailures(page);
  await loadDashboard(page);
  await openSettings(page);

  await page.locator('[data-openmmi-settings-section="system"]').click();
  await expect(page.locator('[data-openmmi-system-settings-panel="true"]')).toBeVisible();
  await expect(page.getByTestId("launcher-default-web")).toHaveClass(/is-selected/);
  await expect(page.getByTestId("launcher-autostart-on")).toHaveClass(/is-selected/);

  await page.getByTestId("launcher-default-tui").click();
  await expect(page.getByTestId("launcher-default-tui")).toHaveClass(/is-selected/);
  await page.getByTestId("launcher-autostart-off").click();
  await expect(page.getByTestId("launcher-autostart-off")).toHaveClass(/is-selected/);

  await page.locator('[data-openmmi-settings-section="media"]').click();
  await expect(page.locator('[data-openmmi-jellyfin-settings="true"]')).toBeVisible();
  const username = page.getByTestId("jellyfin-username");
  await username.click();
  await page.keyboard.type("dr");
  await page.waitForTimeout(1250);
  await expect(username).toBeFocused();
  await page.keyboard.type("h");
  await expect(username).toBeFocused();
  await expect(page.locator("#pageSettings")).toHaveClass(/active/);
  await expect(page.locator('[data-openmmi-settings-section="media"]')).toHaveClass(/active/);
  await expect(username).toHaveValue("drh");

  await page.getByTestId("jellyfin-url").fill("https://jellyfin.test:8096");
  await username.fill("driver");
  await page.getByTestId("jellyfin-password").fill("not-exposed-after-submit");
  await page.getByTestId("jellyfin-test").click();
  await expect(page.getByRole("status")).toContainText("connection succeeded");
  await expect(page.getByTestId("jellyfin-url")).toHaveValue("https://jellyfin.test:8096");
  await expect(page.getByTestId("jellyfin-username")).toHaveValue("driver");
  await expect(page.getByTestId("jellyfin-password")).toHaveValue("not-exposed-after-submit");
  await page.getByTestId("jellyfin-save").click();
  await expect(page.getByRole("status")).toContainText("restart the dashboard");
  await expect(page.getByTestId("jellyfin-password")).toHaveValue("");
  await expect(page.locator('[data-openmmi-jellyfin-settings="true"]')).not.toContainText("not-exposed-after-submit");

  await expectNoRuntimeFailures(failures);
});
