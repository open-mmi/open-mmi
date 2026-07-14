const PAGE_NAMES = ["Drive", "Climate", "Vehicle", "Media"];
const PAGE_IDS = ["pageDrive", "pageClimate", "pageVehicle", "pageElectrical"];
const DOORS = ["front_left", "front_right", "rear_left", "rear_right", "boot", "bonnet"];

const openMmiApiClient = window.openMmiApi;
const openMmiPrefs = window.openMmiPreferences;
const openMmiStatusClient = window.openMmiStatus;
if (!openMmiApiClient || !openMmiPrefs || !openMmiStatusClient) {
  throw new Error("Open MMI frontend modules did not load");
}

const openMmiStatusStore = openMmiStatusClient.createStore();
window.openMmiStatusStore = openMmiStatusStore;

let activePage = 0;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function get(obj, dotted, fallback = undefined) {
  return dotted.split(".").reduce((cur, key) => {
    if (cur && Object.prototype.hasOwnProperty.call(cur, key)) return cur[key];
    return fallback;
  }, obj);
}

function setField(name, value) {
  $$(`[data-field="${name}"]`).forEach((node) => { node.textContent = value; });
}

function fmtNum(value, decimals = 0) {
  if (value === null || value === undefined || value === "-") return "--";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function kmToMi(km, decimals = 0) {
  const n = Number(km);
  if (!Number.isFinite(n)) return "--";
  return fmtNum(n * 0.621371192, decimals);
}

function openMmiApplyDriverFacingCleanup() {
  const removeContainer = (node) => {
    if (!node) return;
    const container = node.closest("article, .tile, .openmmi-home-tile, .openmmi-home-metric, .openmmi-home-status, .metric, .status-chip, .summary-tile, .summary-card");
    if (container && !container.closest(".openmmi-settings-shell")) container.remove();
  };

  const home = document.querySelector("#pageHome");
  if (home) {
    home.querySelectorAll('[data-field="range_mi"], [data-field="rpm"], [data-field="lighting_mode"], [data-field="lights_on"]').forEach(removeContainer);
    home.querySelectorAll("article, .tile, .openmmi-home-tile, .openmmi-home-metric, .openmmi-home-status, .summary-tile, .summary-card").forEach((node) => {
      const label = (node.querySelector(".label, .openmmi-label, .metric-label")?.textContent || "").trim().toLowerCase();
      if (["lights", "light state", "lighting", "range", "range est.", "range est", "rpm"].includes(label)) node.remove();
    });
  }

  document.querySelectorAll('#pageClimate [data-field="outside_unfiltered_c"]').forEach(removeContainer);
}



function openMmiApplyDriverDashboardCleanupV2() {
  const home = document.querySelector("#pageHome");
  if (home) {
    home.querySelectorAll("small").forEach((node) => {
      const text = (node.textContent || "").trim();
      if (text === "Speed, RPM and tell-tales" || text === "Speed, RPM, and tell-tales") {
        node.textContent = "Speed and tell-tales";
      }
    });

    const removeHomeLabels = [/^lights?\b/i, /^range\b/i, /^rpm\b/i, /lights state/i, /range est/i];
    const candidates = home.querySelectorAll([
      "article",
      ".tile",
      ".openmmi-home-tile",
      ".openmmi-home-stat",
      ".openmmi-home-metric",
      ".openmmi-home-status-item",
      "[data-openmmi-home-metric]"
    ].join(","));

    candidates.forEach((node) => {
      if (node.closest("nav") || node.matches("button") || node.closest("button")) return;
      const labelNode = node.querySelector(".label, .openmmi-label, dt, h3, h4, strong, span");
      const label = ((labelNode && labelNode.textContent) || node.textContent || "").trim();
      if (removeHomeLabels.some((pattern) => pattern.test(label))) node.remove();
    });
  }

  const diagnosticsPanel = document.querySelector("#openmmiSettingsPanel");
  if (diagnosticsPanel) {
    diagnosticsPanel.querySelectorAll([
      ".openmmi-settings-row",
      ".openmmi-settings-control",
      ".openmmi-diagnostics-control",
      ".openmmi-diagnostics-row",
      "article",
      "[data-openmmi-diagnostics-control]"
    ].join(",")).forEach((node) => {
      if (node.closest("#openmmiSettingsStaticControls")) return;
      const text = (node.textContent || "").toLowerCase();
      const hasControl = !!node.querySelector("button, [role='button'], .openmmi-settings-pill, .openmmi-pill");
      if (hasControl && (text.includes("raw/debug") || text.includes("raw debug") || text.includes("show raw") || text.includes("hide raw"))) {
        node.remove();
      }
    });
  }
}

function openMmiUnitPrefs() {
  return openMmiPrefs.readDashboardSettings({ speedUnit: "mph", tempUnit: "c" });
}

function openMmiDistanceUnitLabel() {
  return openMmiUnitPrefs().speedUnit === "kmh" ? "km" : "mi";
}

function openMmiSpeedUnitLabel() {
  return openMmiUnitPrefs().speedUnit === "kmh" ? "km/h" : "mph";
}

function openMmiTempUnitLabel() {
  return openMmiUnitPrefs().tempUnit === "f" ? "°F" : "°C";
}

function openMmiFormatSpeedFromKmh(km, decimals = 0) {
  const n = Number(km);
  if (!Number.isFinite(n)) return "--";
  return openMmiUnitPrefs().speedUnit === "kmh" ? fmtNum(n, decimals) : kmToMi(n, decimals);
}

function openMmiFormatDistanceFromKm(km, decimals = 0) {
  const n = Number(km);
  if (!Number.isFinite(n)) return "--";
  return openMmiUnitPrefs().speedUnit === "kmh" ? fmtNum(n, decimals) : kmToMi(n, decimals);
}

function openMmiFormatTempFromC(celsius, decimals = 0) {
  const n = Number(celsius);
  if (!Number.isFinite(n)) return "--";
  const value = openMmiUnitPrefs().tempUnit === "f" ? ((n * 9) / 5) + 32 : n;
  return fmtNum(value, decimals);
}

function openMmiApplyUnitLabels() {
  const labels = {
    speed_mph: openMmiSpeedUnitLabel(),
    odo_mi: openMmiDistanceUnitLabel(),
    range_mi: openMmiDistanceUnitLabel(),
    coolant_c: openMmiTempUnitLabel(),
    outside_reg_c: openMmiTempUnitLabel(),
    outside_unfiltered_c: openMmiTempUnitLabel(),
  };

  Object.entries(labels).forEach(([field, unit]) => {
    document.querySelectorAll(`[data-field="${field}"]`).forEach((node) => {
      const value = node.closest(".value");
      const small = value ? value.querySelector("small") : node.parentElement?.querySelector("small");
      if (small) small.textContent = unit;
    });
  });
}


function boolText(value) {
  if (value === true) return "ON";
  if (value === false) return "OFF";
  return "--";
}

function boolNoText(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "--";
}

function setBool(name, value) {
  $$(`[data-bool="${name}"]`).forEach((node) => { node.textContent = boolText(value); });
}

function setBoolNo(name, value) {
  $$(`[data-bool-no="${name}"]`).forEach((node) => { node.textContent = boolNoText(value); });
}

function updateDoor(name, value) {
  const isOpen = value === true;
  const text = value === true ? "Open" : value === false ? "Closed" : "--";
  $$(`[data-door-text="${name}"]`).forEach((node) => { node.textContent = text; });
  $$(`[data-door-row="${name}"]`).forEach((node) => { node.classList.toggle("open", isOpen); });
  $$(`[data-door-mark="${name}"]`).forEach((node) => { node.classList.toggle("open", isOpen); });
}

function updateHealth(payload) {
  const health = payload.health || {};
  const dot = $("#healthDot");
  dot.className = `health-dot ${health.status || "waiting"}`;
  $("#healthText").textContent = health.status || "waiting";
  $("#ageText").textContent = typeof health.age_seconds === "number" ? `${health.age_seconds.toFixed(1)}s ago` : "--";
}

function indicatorLabel(lighting) {
  if (lighting.hazards === true) return "Hazards";
  if (lighting.left_indicator === true && lighting.right_indicator === true) return "Both";
  if (lighting.left_indicator === true) return "Left";
  if (lighting.right_indicator === true) return "Right";
  if (lighting.left_indicator === false || lighting.right_indicator === false) return "Off";
  return "--";
}

function lightsLabel(value) {
  if (value === true) return "ON";
  if (value === false) return "OFF";
  return "--";
}

function updateTach(rpm) {
  const n = Number(rpm);
  const isKnown = Number.isFinite(n);
  const clamped = isKnown ? Math.max(0, Math.min(6000, n)) : 0;
  const progress = clamped / 6000;
  const root = document.documentElement;

  root.style.setProperty("--rpm-scale", progress.toFixed(4));
  root.style.setProperty("--rpm-fill", `${(progress * 100).toFixed(2)}%`);
  root.classList.remove("rpm-unknown", "rpm-idle", "rpm-normal", "rpm-high", "rpm-redline");

  let state = "rpm-unknown";
  if (isKnown) {
    if (clamped < 900) state = "rpm-idle";
    else if (clamped < 4200) state = "rpm-normal";
    else if (clamped < 5200) state = "rpm-high";
    else state = "rpm-redline";
  }

  root.classList.add(state);
} function render(payload) {
  updateHealth(payload);
  const state = payload.state || {};
  const vehicle = state.vehicle || {};
  const engine = state.engine || {};
  const electrical = state.electrical || {};
  const climate = state.climate || {};
  const lighting = state.lighting || {};
  const fuel = state.fuel || {};
  const doors = state.doors || {};

  setField("speed_mph", openMmiFormatSpeedFromKmh(vehicle.speed_kmh, 0));
  setField("rpm", fmtNum(engine.speed_rpm, 0));
  setField("odo_mi", openMmiFormatDistanceFromKm(vehicle.odometer_km, 0));
  // Fuel-range CAN frame is unverified; retain the field as unknown.
  setField("range_mi", "--");
  setField("coolant_c", openMmiFormatTempFromC(engine.coolant_temp_c, 0));
  setField("outside_reg_c", openMmiFormatTempFromC(climate.outside_temp_regulation_c, 1));
  setField("outside_unfiltered_c", openMmiFormatTempFromC(climate.outside_temp_unfiltered_c, 1));
  openMmiApplyUnitLabels();
  if (typeof openMmiApplyTellTaleTest === "function") openMmiApplyTellTaleTest();
  setField("voltage_v", fmtNum(electrical.supply_voltage_v ?? electrical.terminal30_voltage_v, 1));
  setField("blower_pct", fmtNum(climate.blower_load_percent, 1));
  setField("dimmer_pct", fmtNum(lighting.dimmer_percent ?? lighting.dimmer_percent_mirror, 0));
  setField("lighting_mode", lighting.mode || "--");
  setField("lights_on", lightsLabel(lighting.lights_on));
  setField("indicators", indicatorLabel(lighting));
  openMmiApplyDriverFacingCleanup();

  setBool("handbrake", vehicle.handbrake);
  setBool("reverse", vehicle.reverse);
  setBool("rear_heater", climate.rear_window_heater_requested);
  setBool("recirculation", climate.recirculation_active ?? climate.front_demist_air_request);
  setBool("compressor", climate.compressor_active);
  setBool("hazards", lighting.hazards);
  setBoolNo("bulb_out", lighting.bulb_out);

  DOORS.forEach((name) => updateDoor(name, doors[name]));
  $$(".car-shell").forEach((node) => { node.classList.toggle("any-open", doors.any_open === true); });

  updateTach(engine.speed_rpm);
}


/* open-mmi dashboard ui pass 11: inline data tell-tales */
(function installInlineDataTelltales() {
  "use strict";

  const ICONS = Object.freeze({
    "leftTurn": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMTg1LjEyMzc1IgogICBoZWlnaHQ9IjIwNy45OTk5NSIKICAgaWQ9InN2ZzQzMjkiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC40OC40IHI5OTM5IgogICBzb2RpcG9kaTpkb2NuYW1lPSJBMTZMLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczQzMzEiIC8+CiAgPHNvZGlwb2RpOm5hbWVkdmlldwogICAgIGlkPSJiYXNlIgogICAgIHBhZ2Vjb2xvcj0iI2ZmZmZmZiIKICAgICBib3JkZXJjb2xvcj0iIzY2NjY2NiIKICAgICBib3JkZXJvcGFjaXR5PSIxLjAiCiAgICAgaW5rc2NhcGU6cGFnZW9wYWNpdHk9IjAuMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOnpvb209IjIuOCIKICAgICBpbmtzY2FwZTpjeD0iNjIuMTA3MzAxIgogICAgIGlua3NjYXBlOmN5PSI3Ni4yODI0ODMiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmN1cnJlbnQtbGF5ZXI9ImxheWVyMSIKICAgICBzaG93Z3JpZD0iZmFsc2UiCiAgICAgZml0LW1hcmdpbi10b3A9IjQiCiAgICAgZml0LW1hcmdpbi1sZWZ0PSI0IgogICAgIGZpdC1tYXJnaW4tcmlnaHQ9IjQiCiAgICAgZml0LW1hcmdpbi1ib3R0b209IjQiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIxOTIwIgogICAgIGlua3NjYXBlOndpbmRvdy1oZWlnaHQ9IjExNTMiCiAgICAgaW5rc2NhcGU6d2luZG93LXg9IjEyNzYiCiAgICAgaW5rc2NhcGU6d2luZG93LXk9Ii00IgogICAgIGlua3NjYXBlOndpbmRvdy1tYXhpbWl6ZWQ9IjEiIC8+CiAgPG1ldGFkYXRhCiAgICAgaWQ9Im1ldGFkYXRhNDMzNCI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgICA8ZGM6dGl0bGU+PC9kYzp0aXRsZT4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+CiAgPGcKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIgogICAgIGlkPSJsYXllcjEiCiAgICAgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTExNS42NTY0OCwtMzczLjA5NDQ1KSI+CiAgICA8ZwogICAgICAgaWQ9Imc1Mjk1IgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS45NDE3NDcxLDAsMCwxLjk0MTc0NzEsLTE2Mi42MjUsLTQ1NS40Mjk2MikiPgogICAgICA8cmVjdAogICAgICAgICB5PSI0MzAuMTMxMDQiCiAgICAgICAgIHg9IjE0Ni43NDcwMiIKICAgICAgICAgaGVpZ2h0PSIxMDAuMjY0OTUiCiAgICAgICAgIHdpZHRoPSI4OC40NzkyMSIKICAgICAgICAgaWQ9InJlY3Q1MjkzIgogICAgICAgICBzdHlsZT0iZmlsbDojMDBhMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjczNTA3MjE0O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzM1MSIKICAgICAgICAgZD0ibSAxNDcuNjYzODksNTA1LjkxMTY4IDAsLTIzLjg1MTkgMTUuNzY5MTUsMTUuNjAxOSBjIDguNjczMDMsOC41ODEgMTkuNDczMDMsMTkuMTM5NiAyNCwyMy40NjM2IDQuNTI2OTcsNC4zMjM5IDguMjMwODUsOC4wMzY0IDguMjMwODUsOC4yNSAwLDAuMjEzNSAtMTAuOCwwLjM4ODIgLTI0LDAuMzg4MiBsIC0yNCwwIDAsLTIzLjg1MTggeiBtIDUxLjgzNDA3LDEwLjYwMzIgYyAwLjE4Mzc0LC03LjI4ODMgMC40MTUzLC0xMy4zMzMgMC41MTQ1OCwtMTMuNDMyNiAwLjA5OTMsLTAuMSA3LjkzNzA0LC0wLjMyNDcgMTcuNDE3MjQsLTAuNSBsIDE3LjIzNjczLC0wLjMxODggLTEwZS00LDEzLjc1IC0wLjAwMSwxMy43NSAtMTcuNzUsMCAtMTcuNzUsMCAwLjMzNDA3LC0xMy4yNTE0IHogbSAtMjUuMzM5OTMsLTI0Ljc1NzMgLTEwLjk3MTc1LC0xMS4wMDU5IDExLjczODgxLC0xMS43Mzg4IDExLjczODgsLTExLjczODggMCw1LjE3MzMgYyAwLDguMTU2OSAwLjM3NDc4LDguMzE2MSAxOS41NzE0Myw4LjMxNjEgbCAxNi40Mjg1NywwIDAsMTAgMCwxMCAtMTYuNDI4NTcsMCBjIC0xOC44ODE2MywwIC0xOS41NzE0MywwLjI2NjkgLTE5LjU3MTQzLDcuNTcxNCAwLDIuNDM1NyAtMC4zNDUxNyw0LjQyODYgLTAuNzY3MDUsNC40Mjg2IC0wLjQyMTg4LDAgLTUuNzA0MzUsLTQuOTUyNiAtMTEuNzM4ODEsLTExLjAwNTkgeiBtIC0yNi40OTQxNCwtMzYuNTE3NiAwLC0yNC40NzY1IDI0LjQ3NjM5LDAgMjQuNDc2MzgsMCAtMTYuNDY5NCwxNi4xMzYzIGMgLTkuMDU4MTgsOC44NzQ5IC0yMC4wNzI1NSwxOS44ODk0IC0yNC40NzYzOSwyNC40NzY1IGwgLTguMDA2OTgsOC4zNDAzIDAsLTI0LjQ3NjYgeiBtIDY4Ljc1LDMuNzc1MiAtMTYuNzUsLTAuMzAwMSAwLC0xMi4zOTQgYyAwLC02LjgxNjcgLTAuMjczMTUsLTEzLjEwNTggLTAuNjA2OTksLTEzLjk3NTggLTAuNTM5NzIsLTEuNDA2NSAxLjM5OTY0LC0xLjU4MTggMTcuNSwtMS41ODE4IGwgMTguMTA2OTksMCAwLDE0LjUgYyAwLDcuOTc1IC0wLjMzNzUsMTQuMzk5MSAtMC43NSwxNC4yNzU5IC0wLjQxMjUsLTAuMTIzMyAtOC4yODc1LC0wLjM1OTIgLTE3LjUsLTAuNTI0MiB6IgogICAgICAgICBzdHlsZT0iZmlsbDojMDAwMDAwIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==",
    "rightTurn": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMTgzLjk2MDg5IgogICBoZWlnaHQ9IjIwNy45ODI4NSIKICAgaWQ9InN2ZzQzMjkiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC40OC40IHI5OTM5IgogICBzb2RpcG9kaTpkb2NuYW1lPSJBMTZSLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczQzMzEiIC8+CiAgPHNvZGlwb2RpOm5hbWVkdmlldwogICAgIGlkPSJiYXNlIgogICAgIHBhZ2Vjb2xvcj0iI2ZmZmZmZiIKICAgICBib3JkZXJjb2xvcj0iIzY2NjY2NiIKICAgICBib3JkZXJvcGFjaXR5PSIxLjAiCiAgICAgaW5rc2NhcGU6cGFnZW9wYWNpdHk9IjAuMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOnpvb209IjIuOCIKICAgICBpbmtzY2FwZTpjeD0iNjEuNTQ0OTAzIgogICAgIGlua3NjYXBlOmN5PSI3NS43MDk4NDkiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmN1cnJlbnQtbGF5ZXI9ImxheWVyMSIKICAgICBzaG93Z3JpZD0iZmFsc2UiCiAgICAgZml0LW1hcmdpbi10b3A9IjQiCiAgICAgZml0LW1hcmdpbi1sZWZ0PSI0IgogICAgIGZpdC1tYXJnaW4tcmlnaHQ9IjQiCiAgICAgZml0LW1hcmdpbi1ib3R0b209IjQiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIxOTIwIgogICAgIGlua3NjYXBlOndpbmRvdy1oZWlnaHQ9IjExNTMiCiAgICAgaW5rc2NhcGU6d2luZG93LXg9IjEyNzYiCiAgICAgaW5rc2NhcGU6d2luZG93LXk9Ii00IgogICAgIGlua3NjYXBlOndpbmRvdy1tYXhpbWl6ZWQ9IjEiIC8+CiAgPG1ldGFkYXRhCiAgICAgaWQ9Im1ldGFkYXRhNDMzNCI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgICA8ZGM6dGl0bGU+PC9kYzp0aXRsZT4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+CiAgPGcKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIgogICAgIGlkPSJsYXllcjEiCiAgICAgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTExNi4yMTg4OCwtMzcyLjUzODkyKSI+CiAgICA8ZwogICAgICAgaWQ9Imc1MzE5IgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS45MjE3NTcxLDAsMCwxLjkyMTc1NzEsLTE0NS44MjQzNywtNDQ2Ljk5NDA1KSI+CiAgICAgIDxyZWN0CiAgICAgICAgIHk9IjQyOS44NzMwMiIKICAgICAgICAgeD0iMTM5Ljc5MjI4IgogICAgICAgICBoZWlnaHQ9IjEwMS4zNzEyNyIKICAgICAgICAgd2lkdGg9Ijg4Ljg3MTI2OSIKICAgICAgICAgaWQ9InJlY3Q1MzE3IgogICAgICAgICBzdHlsZT0iZmlsbDojMDBhMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjcwMDE1NzE3O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzM0OSIKICAgICAgICAgZD0ibSAxNDAuNzI3OTEsNTE1Ljg4MDEyIDAsLTE0LjUgMTYuOCwwIGMgMTEuNzMzMzMsMCAxNy4xNjE5LDAuMzYxOSAxOCwxLjIgMC44MTMwMywwLjgxMyAxLjIsNS40ODg5IDEuMiwxNC41IGwgMCwxMy4zIC0xOCwwIC0xOCwwIDAsLTE0LjUgeiBtIDM3LjEwMDkxLDE0LjI1IGMgMC4yMzg4MywtMC4xMzc1IDExLjU2MzgzLC0xMS4yNjI4IDI1LjE2NjY2LC0yNC43MjI5IGwgMjQuNzMyNDMsLTI0LjQ3MjkgMCwyNC43MjI5IDAsMjQuNzIyOSAtMjUuMTY2NjcsMCBjIC0xMy44NDE2NiwwIC0yNC45NzEyNSwtMC4xMTI1IC0yNC43MzI0MiwtMC4yNSB6IG0gMTAuNTIwMTcsLTI5LjI5NTEgYyAtMC4zNDE1OSwtMC44OTAxIC0wLjYyMTA4LC0zLjM4MTcgLTAuNjIxMDgsLTUuNTM2NyBsIDAsLTMuOTE4MiAtMTYuOCwwIGMgLTExLjczMzMzLDAgLTE3LjE2MTkxLC0wLjM2MTkgLTE4LC0xLjIgLTEuNjIwNjksLTEuNjIwNyAtMS42MjA2OSwtMTcuOTc5MyAwLC0xOS42IDAuODM4MDksLTAuODM4MSA2LjI2NjY3LC0xLjIgMTgsLTEuMiBsIDE2LjgsMCAwLC00Ljk0MSBjIDAsLTIuNzE3NSAwLjM5MDU4LC01LjE4MjQgMC44Njc5NiwtNS40Nzc0IDAuNDc3MzgsLTAuMjk1IDUuOTUyNyw0LjMzMDIgMTIuMTY3MzcsMTAuMjc4MyBsIDExLjI5OTQxLDEwLjgxNDYgLTUuOTE3MzcsNS44MDQxIGMgLTE1LjkyNjE2LDE1LjYyMTQgLTE3LjE1MjY4LDE2LjY1MzYgLTE3Ljc5NjI5LDE0Ljk3NjMgeiBtIDMyLjg1OTEyLC0yNy43NzM1IGMgLTMuMzEwODksLTMuMzk5OCAtMTQuMzg1ODUsLTE0LjM5MzkgLTI0LjYxMTAzLC0yNC40MzE0IGwgLTE4LjU5MTIzLC0xOC4yNSAyNC44NjEwMywwIDI0Ljg2MTAzLDAgMCwyNC41IGMgMCwxMy40NzUgLTAuMTEyNSwyNC40NjkxIC0wLjI1LDI0LjQzMTQgLTAuMTM3NSwtMC4wMzggLTIuOTU4OTEsLTIuODUwMiAtNi4yNjk4LC02LjI1IHogbSAtODAuNDgwMiwtMjguMTgxNCAwLC0xNC41IDE4LDAgMTgsMCAwLDEzLjMgYyAwLDkuMDExMSAtMC4zODY5NywxMy42ODcgLTEuMiwxNC41IC0wLjgzODEsMC44MzgxIC02LjI2NjY3LDEuMiAtMTgsMS4yIGwgLTE2LjgsMCAwLC0xNC41IHoiCiAgICAgICAgIHN0eWxlPSJmaWxsOiMwMDAwMDAiIC8+CiAgICA8L2c+CiAgPC9nPgo8L3N2Zz4K",
    "bulbFailure": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMjA4IgogICBoZWlnaHQ9IjE5Mi43OTM2NCIKICAgaWQ9InN2ZzQzMjkiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC40OC40IHI5OTM5IgogICBzb2RpcG9kaTpkb2NuYW1lPSJBMTQuc3ZnIj4KICA8ZGVmcwogICAgIGlkPSJkZWZzNDMzMSIgLz4KICA8c29kaXBvZGk6bmFtZWR2aWV3CiAgICAgaWQ9ImJhc2UiCiAgICAgcGFnZWNvbG9yPSIjZmZmZmZmIgogICAgIGJvcmRlcmNvbG9yPSIjNjY2NjY2IgogICAgIGJvcmRlcm9wYWNpdHk9IjEuMCIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMC4wIgogICAgIGlua3NjYXBlOnBhZ2VzaGFkb3c9IjIiCiAgICAgaW5rc2NhcGU6em9vbT0iMi44IgogICAgIGlua3NjYXBlOmN4PSI3NC41MjU3NzUiCiAgICAgaW5rc2NhcGU6Y3k9Ijg2LjU5ODc3MiIKICAgICBpbmtzY2FwZTpkb2N1bWVudC11bml0cz0icHgiCiAgICAgaW5rc2NhcGU6Y3VycmVudC1sYXllcj0ibGF5ZXIxIgogICAgIHNob3dncmlkPSJmYWxzZSIKICAgICBmaXQtbWFyZ2luLXRvcD0iNCIKICAgICBmaXQtbWFyZ2luLWxlZnQ9IjQiCiAgICAgZml0LW1hcmdpbi1yaWdodD0iNCIKICAgICBmaXQtbWFyZ2luLWJvdHRvbT0iNCIKICAgICBpbmtzY2FwZTp3aW5kb3ctd2lkdGg9IjE5MjAiCiAgICAgaW5rc2NhcGU6d2luZG93LWhlaWdodD0iMTE1MyIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iMTI3NiIKICAgICBpbmtzY2FwZTp3aW5kb3cteT0iLTQiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0iMSIgLz4KICA8bWV0YWRhdGEKICAgICBpZD0ibWV0YWRhdGE0MzM0Ij4KICAgIDxyZGY6UkRGPgogICAgICA8Y2M6V29yawogICAgICAgICByZGY6YWJvdXQ9IiI+CiAgICAgICAgPGRjOmZvcm1hdD5pbWFnZS9zdmcreG1sPC9kYzpmb3JtYXQ+CiAgICAgICAgPGRjOnR5cGUKICAgICAgICAgICByZGY6cmVzb3VyY2U9Imh0dHA6Ly9wdXJsLm9yZy9kYy9kY21pdHlwZS9TdGlsbEltYWdlIiAvPgogICAgICAgIDxkYzp0aXRsZT48L2RjOnRpdGxlPgogICAgICA8L2NjOldvcms+CiAgICA8L3JkZjpSREY+CiAgPC9tZXRhZGF0YT4KICA8ZwogICAgIGlua3NjYXBlOmxhYmVsPSJMYXllciAxIgogICAgIGlua3NjYXBlOmdyb3VwbW9kZT0ibGF5ZXIiCiAgICAgaWQ9ImxheWVyMSIKICAgICB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMTAzLjIzODAxLC0zOTguNjE3MDUpIj4KICAgIDxnCiAgICAgICBpZD0iZzUyMjMiCiAgICAgICB0cmFuc2Zvcm09Im1hdHJpeCgxLjAxMzc1ODIsMCwwLDEuMDEzNzU4MiwtMS40NzUzOTc4LC04LjA4MTY5MDkpIj4KICAgICAgPHJlY3QKICAgICAgICAgeT0iNDA2LjQ5MiIKICAgICAgICAgeD0iMTA4LjYwNTA2IgogICAgICAgICBoZWlnaHQ9IjE3OS41NTE2MSIKICAgICAgICAgd2lkdGg9IjE5NC41NTE2MSIKICAgICAgICAgaWQ9InJlY3Q1MjIxIgogICAgICAgICBzdHlsZT0iZmlsbDojZTBiMzAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjczNDEwNjA2O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzI5OSIKICAgICAgICAgZD0ibSAxMDkuMzgwODgsNTQwLjE1MTA3IDAsLTQ1LjQ3NCAxNS4yNSwtMC4yNzYwNCAxNS4yNSwtMC4yNzYwNSAwLC01IDAsLTUgLTE1LjI1LC0wLjI3NjA1IC0xNS4yNSwtMC4yNzYwNCAwLC0zNy45NzM5NiAwLC0zNy45NzM5NSAzNSwwIDM1LDAgMCwxNy4wMDY2MSAwLDE3LjAwNjYyIC0yLjc1LDIuMjI3OTUgYyAtMS41MTI1LDEuMjI1MzggLTUuNDc1MzUsNC45MzU0MyAtOC44MDYzNSw4LjI0NDU3IC0xMC45MzAxNiwxMC44NTg0MyAtMTYuNDk0LDI2LjMwMzAzIC0xNS4wNTQ2NCw0MS43ODk5NyAyLjAxNjY2LDIxLjY5ODUzIDE1LjU2NjU1LDM4Ljk2MTExIDM2LjMzNDg1LDQ2LjI5MDY3IDUuNDk2NTYsMS45Mzk4IDguNzU4OTIsMi4zOTE0IDE3LjI3NjE0LDIuMzkxNCA4LjU5MTM2LDAgMTEuNzY0MjgsLTAuNDQ2MSAxNy40NTUxNywtMi40NTQgMjYuNTkzMTQsLTkuMzgyODMgNDEuMjk5MzcsLTM3LjE5NzAzIDM0LjM2OTUzLC02NS4wMDM3OSAtMS4zMTM3NCwtNS4yNzE1NiAtNi4yNzQ5OSwtMTUuMDE4MTMgLTEwLjEwODE4LC0xOS44NTc5MyAtMS42ODcwOSwtMi4xMzAxMiAtNS4zNTA5OCwtNS42MjQ3IC04LjE0MTk4LC03Ljc2NTczIC0yLjc5MSwtMi4xNDEwMyAtNS42MzcwNCwtNC4zNTY4MyAtNi4zMjQ1NCwtNC45MjM5OSAtMC45MTAzMywtMC43NTA5OSAtMS4yNSwtNS42Mzk5NiAtMS4yNSwtMTcuOTkxNzggbCAwLC0xNi45NjA1NyAzNSwwIDM1LDAgMCwzNy45NzMyNyAwLDM3Ljk3MzI2IC0xNC43NSwwLjI3Njc0IC0xNC43NSwwLjI3NjczIDAsNSAwLDUgMTQuNzUsMC4yNzY3MyAxNC43NSwwLjI3Njc0IDAsNDUuNDczMjIgMCw0NS40NzMzIC00NS40NzMyNywwIC00NS40NzMyNiwwIC0wLjI3Njc0LC0xNC43NSAtMC4yNzY3MywtMTQuNzUgLTUsMCAtNSwwIC0wLjI3NjczLDE0Ljc1IC0wLjI3Njc0LDE0Ljc1IC00NS40NzMyNiwwIC00NS40NzMyNywwIDAsLTQ1LjQ3MzkgeiBtIDQzLjk4MTc3LDkuOTkyMiAxMC40NDYwMywtMTAuNDgxNyAtMy40MTAwNywtMy41MTgzIGMgLTEuODc1NTMsLTEuOTM1MSAtMy44OTIzMywtMy41MTgyOSAtNC40ODE3NiwtMy41MTgyOSAtMC41ODk0NCwwIC01Ljc3MjQyLDQuNzE2NzkgLTExLjUxNzc0LDEwLjQ4MTY5IGwgLTEwLjQ0NjAzLDEwLjQ4MTcgMy40MTAwNywzLjUxODMgYyAxLjg3NTUzLDEuOTM1MSAzLjg5MjMzLDMuNTE4MyA0LjQ4MTc2LDMuNTE4MyAwLjU4OTQ0LDAgNS43NzI0MiwtNC43MTY4IDExLjUxNzc0LC0xMC40ODE3IHogbSAxMjEuMjEzNTEsNy43OTQ2IGMgMS41NDI2LC0xLjQ3NzkgMi44MDQ3MiwtMy4yNTI5IDIuODA0NzIsLTMuOTQ0NCAwLC0xLjI5ODIgLTE5LjYyNTE4LC0yMS4zNjg0OSAtMjAuODk0NjQsLTIxLjM2ODQ5IC0wLjM5MjE3LDAgLTIuMjQ3NTYsMS41ODMxOSAtNC4xMjMwOSwzLjUxODI5IGwgLTMuNDEwMDcsMy41MTgzIDEwLjQ0NjAzLDEwLjQ4MTcgYyA1Ljc0NTMyLDUuNzY0OSAxMC44Nzk0NSwxMC40ODE3IDExLjQwOTE4LDEwLjQ4MTcgMC41Mjk3NCwwIDIuMjI1MjgsLTEuMjA5MiAzLjc2Nzg3LC0yLjY4NzEgeiBtIC0xMTUsLTExNC45OTk5OCBjIDEuNTQyNiwtMS40Nzc5IDIuODA0NzIsLTMuMjU2MzIgMi44MDQ3MiwtMy45NTIwNCAwLC0xLjYwMzk0IC0xOS4wNTQ5OCwtMjAuMzYwODcgLTIwLjY4NDQsLTIwLjM2MDg3IC0xLjcwNTExLDAgLTYuMzE1Niw0LjQ1MDc1IC02LjMxNTYsNi4wOTY3OCAwLDEuNTM2NzkgMTguOTI0NzgsMjAuOTAzMjIgMjAuNDI2NTIsMjAuOTAzMjIgMC41MzAyMiwwIDIuMjI2MTcsLTEuMjA5MTkgMy43Njg3NiwtMi42ODcwOSB6IG0gMTA4LjAzNjgzLC03LjA0NDE1IGMgNS4zNzIzNCwtNS4zNTIxOCA5Ljc2Nzg5LC0xMC4yMTM5IDkuNzY3ODksLTEwLjgwMzgzIDAsLTAuNTg5OTMgLTEuNTg1OTcsLTIuNjA5NzggLTMuNTI0MzgsLTQuNDg4NTcgbCAtMy41MjQzOSwtMy40MTU5NiAtMTAuNjk1NDIsMTAuNjk1NDEgLTEwLjY5NTQxLDEwLjY5NTQyIDMuNDE1OTcsMy41MjQzOCBjIDEuODc4NzgsMS45Mzg0MiAzLjg4MjE0LDMuNTI0MzkgNC40NTE5MSwzLjUyNDM5IDAuNTY5NzYsMCA1LjQzMTQ5LC00LjM3OTA2IDEwLjgwMzgzLC05LjczMTI0IHogbSAtNzIuNDg2MTksOTUuNzA3NDkgYyAtMTAuNzcwMDIsLTIuNzE1OTUgLTIyLjg3NzQzLC0xMi42NTkxOCAtMjcuOTc3MTIsLTIyLjk3NjI1IC0xLjQ5NTI1LC0zLjAyNSAtMy4yNzA4MSwtOC43NTgzNyAtMy45NDU2OSwtMTIuNzQwODEgLTAuOTczNjksLTUuNzQ1NzEgLTAuOTcwMDEsLTguNTMzMjQgMC4wMTc4LC0xMy41IDEuNzM0MzIsLTguNzIwMDggNi42NDYzMywtMTguMzQxNyAxMi4xOTc5NywtMjMuODkzMzQgNy43MDE2OSwtNy43MDE2OSAxOS44NjgwNiwtMTIuODI4OTQgMzAuNTAwOTksLTEyLjg1Mzk4IDYuNTI0OSwtMC4wMTU0IDE1LjUzMzQ3LDIuMzU4OTcgMjEuNzE0NzEsNS43MjMyMiA1LjY4NjQ3LDMuMDk0OTcgMTQuODUwMzgsMTIuNTkwMjIgMTcuODc3NTQsMTguNTIzOTUgMS4xNTEyNCwyLjI1NjYgMi42OTk2Myw3LjU3NjkxIDMuNDQwODgsMTEuODIyOTEgMC45OTU5Myw1LjcwNDgxIDEuMDg5ODQsOS4zNzczIDAuMzU5NzYsMTQuMDY5MDIgLTIuMTg5MjMsMTQuMDY4NzMgLTExLjg4NjM0LDI3LjEyNDYzIC0yNC41NDY5LDMzLjA0OTIyIC01Ljc1Mjg4LDIuNjkyMSAtNy45NzMxNywzLjE1ODcxIC0xNi4yNzM4MywzLjQyMDA5IC01LjI4NjYzLDAuMTY2NDcgLTExLjMwMTM5LC0wLjEyMzM0IC0xMy4zNjYxMywtMC42NDQwMyB6IG0gMTYuNTA0MDgsLTEwLjEyOTY4IGMgMC45NjI1LC0xLjEzNzQ3IDEuNzUsLTMuMTYzNzQgMS43NSwtNC41MDI4MSAwLC0zLjE4MTgxIC00LjIyNDczLC03LjM0Mzc2IC03LjQ1NDU1LC03LjM0Mzc2IC0zLjYyMzQ5LDAgLTYuNTQ1NDUsMy4zMTU2NyAtNi41NDU0NSw3LjQyNzQyIDAsMi41MzQ2NSAwLjcwNTA0LDMuOTgyMDEgMi43MDY3Miw1LjU1NjUyIDMuMTY2MDksMi40OTA0NiA2Ljg0NDQ4LDIuMDUyMDcgOS41NDMyOCwtMS4xMzczNyB6IG0gLTAuNzA0NTUsLTE4LjMwMTEyIDIuNDU0NTUsLTIuNDU0NTQgMCwtMjEuOTM0NjcgYyAwLC0xOS44MjY4OCAtMC4xNzcyMSwtMjIuMTUzNTIgLTEuODQ0MTcsLTI0LjIxMjEyIC0yLjUwNzI3LC0zLjA5NjM2IC03LjgwNDM5LC0zLjA5NjM2IC0xMC4zMTE2NiwwIC0xLjY2OTEsMi4wNjEyNSAtMS44NDQxNyw0LjM5NiAtMS44NDQxNywyNC41OTQwOCBsIDAsMjIuMzE2NjQgMi42MzQ4NiwyLjA3MjU4IGMgMS40NDkxNywxLjEzOTkyIDMuNDk0NjMsMi4wNzI1OCA0LjU0NTQ1LDIuMDcyNTggMS4wNTA4MywwIDMuMDE1MTQsLTEuMTA0NTUgNC4zNjUxNCwtMi40NTQ1NSB6IG0gNC45NTQ1NSwtNjYuNzM4IGMgLTIuMjI1MTEsLTAuNTQ1NjEgLTguNzg2NzksLTAuNzExNjEgLTE0Ljc4Nzc5LC0wLjM3NDA5IGwgLTEwLjc4Nzc5LDAuNjA2NzMgMC4yODc3OSwtOS4yNzAwNCAwLjI4Nzc5LC05LjI3MDA1IDE1LjUsMCAxNS41LDAgMCw5LjQxNjY3IGMgMCw1LjQ1OTQ2IC0wLjQyMDIzLDkuNTEyMjYgLTEsOS42NDQxNCAtMC41NSwwLjEyNTExIC0yLjgsLTAuMjEzOSAtNSwtMC43NTMzNiB6IgogICAgICAgICBzdHlsZT0iZmlsbDojMDAwMDAwIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==",
    "hazard": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMjA4IgogICBoZWlnaHQ9IjE3Ny43MDk3IgogICBpZD0ic3ZnNDMyOSIKICAgdmVyc2lvbj0iMS4xIgogICBpbmtzY2FwZTp2ZXJzaW9uPSIwLjQ4LjQgcjk5MzkiCiAgIHNvZGlwb2RpOmRvY25hbWU9IkExOS5zdmciPgogIDxkZWZzCiAgICAgaWQ9ImRlZnM0MzMxIiAvPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBpZD0iYmFzZSIKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMS4wIgogICAgIGlua3NjYXBlOnBhZ2VvcGFjaXR5PSIwLjAiCiAgICAgaW5rc2NhcGU6cGFnZXNoYWRvdz0iMiIKICAgICBpbmtzY2FwZTp6b29tPSIyLjgiCiAgICAgaW5rc2NhcGU6Y3g9IjU4LjExNjM0MiIKICAgICBpbmtzY2FwZTpjeT0iNDUuNDk1NTM3IgogICAgIGlua3NjYXBlOmRvY3VtZW50LXVuaXRzPSJweCIKICAgICBpbmtzY2FwZTpjdXJyZW50LWxheWVyPSJsYXllcjEiCiAgICAgc2hvd2dyaWQ9ImZhbHNlIgogICAgIGZpdC1tYXJnaW4tdG9wPSI0IgogICAgIGZpdC1tYXJnaW4tbGVmdD0iNCIKICAgICBmaXQtbWFyZ2luLXJpZ2h0PSI0IgogICAgIGZpdC1tYXJnaW4tYm90dG9tPSI0IgogICAgIGlua3NjYXBlOndpbmRvdy13aWR0aD0iMTkyMCIKICAgICBpbmtzY2FwZTp3aW5kb3ctaGVpZ2h0PSIxMTUzIgogICAgIGlua3NjYXBlOndpbmRvdy14PSIxMjc2IgogICAgIGlua3NjYXBlOndpbmRvdy15PSItNCIKICAgICBpbmtzY2FwZTp3aW5kb3ctbWF4aW1pemVkPSIxIiAvPgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTQzMzQiPgogICAgPHJkZjpSREY+CiAgICAgIDxjYzpXb3JrCiAgICAgICAgIHJkZjphYm91dD0iIj4KICAgICAgICA8ZGM6Zm9ybWF0PmltYWdlL3N2Zyt4bWw8L2RjOmZvcm1hdD4KICAgICAgICA8ZGM6dHlwZQogICAgICAgICAgIHJkZjpyZXNvdXJjZT0iaHR0cDovL3B1cmwub3JnL2RjL2RjbWl0eXBlL1N0aWxsSW1hZ2UiIC8+CiAgICAgICAgPGRjOnRpdGxlPjwvZGM6dGl0bGU+CiAgICAgIDwvY2M6V29yaz4KICAgIDwvcmRmOlJERj4KICA8L21ldGFkYXRhPgogIDxnCiAgICAgaW5rc2NhcGU6bGFiZWw9IkxheWVyIDEiCiAgICAgaW5rc2NhcGU6Z3JvdXBtb2RlPSJsYXllciIKICAgICBpZD0ibGF5ZXIxIgogICAgIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0xMTkuNjQ3NDQsLTM3Mi41OTc3NSkiPgogICAgPGcKICAgICAgIGlkPSJnNTM1NCIKICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KDEuMTc3OTU1NSwwLDAsMS4xNzc5NTU1LC0yMi4wMDM3NCwtOTcuMjE4NDA2KSI+CiAgICAgIDxyZWN0CiAgICAgICAgIHk9IjQwMy42MzM4MiIKICAgICAgICAgeD0iMTI1LjA0NTIyIgogICAgICAgICBoZWlnaHQ9IjE0MS4yNzU4NSIKICAgICAgICAgd2lkdGg9IjE2Ni45OTAxNCIKICAgICAgICAgaWQ9InJlY3Q1MzQxIgogICAgICAgICBzdHlsZT0iZmlsbDojY2YwMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjc5NTU2MDM2O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzM3NyIKICAgICAgICAgZD0ibSAyODguNDkxOTksNTQxLjc1NzUyIGMgLTEuMDkzMSwtMS40NDE3NiAtMTAuMzU0MSwtMTcuMDc5MjYgLTIwLjU4LC0zNC43NSAtMTAuMjI1OSwtMTcuNjcwNzMgLTIwLjYyNTEsLTM1LjUwMzYxIC0yMy4xMDkyLC0zOS42Mjg2MSAtMi40ODQyLC00LjEyNSAtMTEuNjEzMSwtMTkuNzgwNjYgLTIwLjI4NjQsLTM0Ljc5MDM1IC04LjY3MzMsLTE1LjAwOTY5IC0xNi4yMjY5LC0yNy4xMzc5NSAtMTYuNzg1NywtMjYuOTUxNjkgLTAuNTU4OCwwLjE4NjI2IC04LjgyNzgsMTMuODE2OTIgLTE4LjM3NTcsMzAuMjkwMzUgLTkuNTQ3OCwxNi40NzM0MyAtMTkuMzIzLDMzLjEwMTY5IC0yMS43MjI3LDM2Ljk1MTY5IC0yLjM5OTYsMy44NSAtMTIuMTM2NCwyMC41IC0yMS42MzczLDM3IC05LjUwMDgsMTYuNSAtMTguMTEwNCwzMC44MDUwMyAtMTkuMTMyMywzMS43ODg5NiAtMS44MTAxLDEuNzQyNzcgLTEuODU4MSwtMC4wMzE5IC0xLjg1ODEsLTY4Ljc1MDAxIGwgMCwtNzAuNTM4OTUgNDEsMCBjIDI2LjY2NjcsMCA0MSwwLjM0OTU5IDQxLDEgMCwwLjU1IDAuNDc2NiwxIDEuMDU5LDEgMC41ODI1LDAgMC43ODA5LC0wLjQ1IDAuNDQxLC0xIC0wLjQwODIsLTAuNjYwNTQgMTMuNDg5NiwtMSA0MC45NDEsLTEgbCA0MS41NTksMCAwLDcxIGMgMCwzOS4wNSAtMC4xMTgyLDcxIC0wLjI2MjYsNzEgLTAuMTQ0NSwwIC0xLjE1NywtMS4xNzk2MiAtMi4yNSwtMi42MjEzOSB6IG0gLTE0NS45NjkyLC02LjM0OTI0IGMgLTAuMzMsLTAuNTMzODUgMC4wNDksLTIuMjIxMzUgMC44NDIyLC0zLjc1IDEuODM2MSwtMy41Mzg1OSAzMC42MjEyLC01Mi44NjU1OSAzNy44MDI0LC02NC43NzkzNyAyLjk4MzcsLTQuOTUgOS44ODc2LC0xNi43NjI1IDE1LjM0MiwtMjYuMjUgNS40NTQ0LC05LjQ4NzUgMTAuNDkwOCwtMTcuMjUgMTEuMTkyLC0xNy4yNSAxLjU2OTIsMCAzLjM1MDcsMi43ODY0NiAxNi4zMDMyLDI1LjUgNS42NDU1LDkuOSAxMS40MTUyLDE5LjggMTIuODIxNiwyMiA3LjczNTUsMTIuMTAwODYgMzYuMTc4NCw2Mi4xODc3NSAzNi4xNzg0LDYzLjcwODkgMCwxLjcwMzA4IC0zLjE5MTQsMS43OTExIC02NC45NDEsMS43OTExIC00MC45MDU0LDAgLTY1LjE2MywtMC4zNTkyNSAtNjUuNTQwOCwtMC45NzA2MyB6IG0gMTEwLjQ4MTgsLTExLjk2NDg5IGMgMCwtMS4wNDcwMyAtMjQuNzc2MSwtNDQuMzIwODcgLTI4Ljk1MDMsLTUwLjU2NDQ4IC0zLjYyMDEsLTUuNDE0ODEgLTEzLjgxMTQsLTIyLjcxNTQ4IC0xNC42MTU3LC0yNC44MTE0MiAtMC4zNTY0LC0wLjkyODcyIC0xLjAwNSwtMS42ODg1OCAtMS40NDEzLC0xLjY4ODU4IC0wLjQzNjQsMCAtMy44Mzk4LDUuMjg3NSAtNy41NjMxLDExLjc1IC0zLjcyMzQsNi40NjI1IC03LjY5NTEsMTMuMDg3NTQgLTguODI2MSwxNC43MjIzMiAtNC4zODk1LDYuMzQ0ODcgLTI5LjMyNyw1MC40NzA4OSAtMjguODEzNCw1MC45ODQ0MyAwLjk4MjYsMC45ODI2NCA5MC4yMDk5LDAuNTk0NjUgOTAuMjA5OSwtMC4zOTIyNyB6IG0gLTc0LjUzLC05LjExMjk5IGMgLTEuMDk1NCwtMS43NzIzOSAyNy4yMzcsLTQ5Ljk1MTQ5IDI5LjM3NDYsLTQ5Ljk1MTQ5IDEuMjM3OSwwIDQuMjkwNCw0Ljc4NDk3IDE4LjE2MDYsMjguNDY3ODQgNi42MzcyLDExLjMzMjg1IDExLjc5OTcsMjEuMDM4NzYgMTEuNDcyMiwyMS41Njg2OCAtMC44NDc3LDEuMzcxNjcgLTU4LjE1ODEsMS4yODkxIC01OS4wMDc0LC0wLjA4NSB6IgogICAgICAgICBzdHlsZT0iZmlsbDojMDAwMDAwIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==",
    "parkingBrake": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjxzdmcKICAgeG1sbnM6ZGM9Imh0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvIgogICB4bWxuczpjYz0iaHR0cDovL2NyZWF0aXZlY29tbW9ucy5vcmcvbnMjIgogICB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiCiAgIHhtbG5zOnN2Zz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciCiAgIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgdmVyc2lvbj0iMS4wIgogICB3aWR0aD0iMjA4IgogICBoZWlnaHQ9IjE2My4xMTI1MiIKICAgdmlld0JveD0iMCAwIDE2Ni40IDEzMC40OTAwMSIKICAgcHJlc2VydmVBc3BlY3RSYXRpbz0ieE1pZFlNaWQgbWVldCIKICAgaWQ9InN2ZzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuNDguNCByOTkzOSIKICAgc29kaXBvZGk6ZG9jbmFtZT0iQjAyLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczE4IiAvPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMSIKICAgICBvYmplY3R0b2xlcmFuY2U9IjEwIgogICAgIGdyaWR0b2xlcmFuY2U9IjEwIgogICAgIGd1aWRldG9sZXJhbmNlPSIxMCIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOndpbmRvdy13aWR0aD0iMTkyMCIKICAgICBpbmtzY2FwZTp3aW5kb3ctaGVpZ2h0PSIxMTUzIgogICAgIGlkPSJuYW1lZHZpZXcxNiIKICAgICBzaG93Z3JpZD0iZmFsc2UiCiAgICAgZml0LW1hcmdpbi10b3A9IjQiCiAgICAgZml0LW1hcmdpbi1sZWZ0PSI0IgogICAgIGZpdC1tYXJnaW4tcmlnaHQ9IjQiCiAgICAgZml0LW1hcmdpbi1ib3R0b209IjQiCiAgICAgaW5rc2NhcGU6em9vbT0iMy4zMzU3OTQ1IgogICAgIGlua3NjYXBlOmN4PSIxMjMuNDY1NjQiCiAgICAgaW5rc2NhcGU6Y3k9IjEwNy4xNjE4MiIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iMTI3NiIKICAgICBpbmtzY2FwZTp3aW5kb3cteT0iLTQiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0iMSIKICAgICBpbmtzY2FwZTpjdXJyZW50LWxheWVyPSJzdmcyIiAvPgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTQiPgpDcmVhdGVkIGJ5IHBvdHJhY2UgMS4xMSwgd3JpdHRlbiBieSBQZXRlciBTZWxpbmdlciAyMDAxLTIwMTMKPHJkZjpSREY+CiAgPGNjOldvcmsKICAgICByZGY6YWJvdXQ9IiI+CiAgICA8ZGM6Zm9ybWF0PmltYWdlL3N2Zyt4bWw8L2RjOmZvcm1hdD4KICAgIDxkYzp0eXBlCiAgICAgICByZGY6cmVzb3VyY2U9Imh0dHA6Ly9wdXJsLm9yZy9kYy9kY21pdHlwZS9TdGlsbEltYWdlIiAvPgogICAgPGRjOnRpdGxlPjwvZGM6dGl0bGU+CiAgPC9jYzpXb3JrPgo8L3JkZjpSREY+CjwvbWV0YWRhdGE+CiAgPHJlY3QKICAgICBzdHlsZT0iZmlsbDojY2YwMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoxLjg1MDU4NzAxO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lIgogICAgIGlkPSJyZWN0Mjk5NSIKICAgICB3aWR0aD0iMTU4LjE0OTQxIgogICAgIGhlaWdodD0iMTIyLjIzOTQzIgogICAgIHg9IjQuMTI1MjkzNyIKICAgICB5PSI0LjEyNTI5MTMiIC8+CiAgPGcKICAgICB0cmFuc2Zvcm09Im1hdHJpeCgwLjA4MTM3Nzk5LDAsMCwtMC4wODEzNzc5OSw0LjE1ODk1ODQsMTI2LjMzMTA0KSIKICAgICBpZD0iZzYiCiAgICAgc3R5bGU9ImZpbGw6IzAwMDAwMDtzdHJva2U6bm9uZSI+CiAgICA8cGF0aAogICAgICAgZD0iTSAxLDExNzMgQyAyLDk5MiA1LDg1OSA3LDg3NSBjIDI0LDE5MyAxMTksMzk3IDI1Miw1MzggbCAzNSwzNyAzOCwtMzcgYyAyMSwtMjAgMzgsLTQwIDM4LC00NCAwLC01IC0xNiwtMjUgLTM2LC00NiBDIDExMiwxMDg2IDUzLDcwNSAxOTEsNDAyIDIyNywzMjEgMjc0LDI1MCAzMzUsMTgyIEwgMzgxLDEzMSAzNDksOTAgQyAzMzEsNjggMzEzLDUwIDMwOSw1MCAyOTIsNTAgMTgyLDE4NSAxMzMsMjY2IDc4LDM1OCAyNiw1MDQgMTEsNjA1IDUsNjQ3IDIsNTYzIDEsMzMzIEwgMCwwIDQ0MywxIGMgMjU3LDEgNDIyLDUgMzk1LDkgLTIyNCwzOCAtNDI3LDE4OCAtNTM2LDM5NSAtNjMsMTE5IC03NywxODQgLTc3LDM1MCAxLDEzNSAzLDE1OCAyNywyMjggMzcsMTExIDEwMCwyMTEgMTg3LDI5OCAxMTEsMTExIDIzNSwxNzggMzg2LDIwOSAyMyw0IC0xNDAsOCAtMzkyLDkgbCAtNDMzLDEgMSwtMzI3IHoiCiAgICAgICBpZD0icGF0aDgiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgPHBhdGgKICAgICAgIGQ9Im0gMTEwMCwxNDkzIGMgNDQsLTcgMTUzLC00NSAyMDUsLTcxIDE3OSwtODggMzE3LC0yNTAgMzgyLC00NDcgMjMsLTcxIDI2LC05NiAyNywtMjIwIDAsLTExOSAtMywtMTUxIC0yMywtMjE1IEMgMTYwNywyNjcgMTM3Myw1NiAxMTAyLDEwIDEwNzUsNiAxMjQwLDIgMTQ5OCwxIGwgNDQyLC0xIC0xLDM1MyBjIC0xLDIyMyAtNCwzMjggLTksMjg2IEMgMTkwNyw0NDIgMTgxNiwyNDUgMTY4MSw5OSBsIC00OSwtNTQgLTI3LDI1IGMgLTUyLDQ4IC01MSw1NCAxNCwxMzIgMjczLDMyNCAyNjcsODAzIC0xMywxMTE1IGwgLTQ1LDUwIDQzLDQyIDQzLDQyIDQzLC00OCBjIDEyOSwtMTQ1IDIxNywtMzQyIDI0MCwtNTMyIDUsLTQyIDgsNjAgOSwyODIgbCAxLDM0NyAtNDMyLC0xIGMgLTIzOCwtMSAtNDIyLC00IC00MDgsLTYgeiIKICAgICAgIGlkPSJwYXRoMTAiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgPHBhdGgKICAgICAgIGQ9Ik0gODEwLDEzNzQgQyA1ODAsMTMxNSAzOTIsMTEyMCAzNDAsODkwIDMyNSw4MjIgMzI4LDY2MiAzNDUsNTk1IDM5NCw0MDQgNTQ1LDIyOSA3MjYsMTU2IGMgMTg1LC03NSA0MTUsLTU2IDU4MSw0OSAxMjUsNzkgMjI3LDIwOSAyNzQsMzUwIDIxLDYwIDI0LDg4IDIzLDIwMCAtMSwxMTQgLTQsMTM5IC0yNywyMDQgLTc0LDIwNyAtMjQyLDM2MSAtNDUyLDQxNiAtNzQsMTkgLTI0MSwxOSAtMzE1LC0xIHogbSAzMDUsLTE5NiBjIDgxLC0xNiAxNDMsLTYwIDE3OCwtMTI4IDI3LC01MSAyOSwtNjIgMjUsLTE0MCAtNSwtMTE0IC00NCwtMTc3IC0xNDMsLTIyOCAtNDUsLTI0IC02MywtMjYgLTE5MiwtMzAgbCAtMTQzLC00IDAsLTE2NCAwLC0xNjQgLTU1LDAgLTU1LDAgMCw0MzUgMCw0MzUgMTYzLDAgYyA5MCwwIDE5MCwtNSAyMjIsLTEyIHoiCiAgICAgICBpZD0icGF0aDEyIgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIgLz4KICAgIDxwYXRoCiAgICAgICBkPSJtIDg0MCw5MjAgMCwtMTYwIDEyMCwwIGMgMTM5LDAgMTY0LDkgMjEwLDcyIDU3LDc4IDMzLDE4OSAtNTAsMjMwIC0yOCwxNCAtNjEsMTggLTE1NywxOCBsIC0xMjMsMCAwLC0xNjAgeiIKICAgICAgIGlkPSJwYXRoMTQiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogIDwvZz4KPC9zdmc+Cg=="
});

  function qsa(selector) {
    return Array.from(document.querySelectorAll(selector));
  }

  function stateClass(value) {
    if (value === true) return "is-active";
    if (value === false) return "is-inactive";
    return "is-unknown";
  }

  function stateText(value) {
    if (value === true) return "on";
    if (value === false) return "off";
    return "unknown";
  }

  function sr(text) {
    return `<span class="openmmi-telltale-sr">${text}</span>`;
  }

  function icon(kind, value, label, src) {
    const status = stateText(value);
    const title = `${label}: ${status}`;
    return `<span class="openmmi-telltale openmmi-telltale-${kind} ${stateClass(value)}" role="img" aria-label="${title}" title="${title}">` +
      `<img src="${src}" alt="" aria-hidden="true" loading="eager" decoding="async" draggable="false" onerror="this.closest('.openmmi-telltale').classList.add('icon-load-failed')">` +
      sr(title) +
      `</span>`;
  }

  function markHost(node, kind, label) {
    node.classList.add("openmmi-telltale-value", `openmmi-telltale-value-${kind}`);
    node.setAttribute("aria-label", label);
    const host = node.closest(".tile, .footer-item");
    if (host) {
      host.classList.add("openmmi-telltale-host", `openmmi-telltale-host-${kind}`);
      host.setAttribute("title", label);
    }
  }

  function setNodeIcon(selector, kind, value, label, src) {
    qsa(selector).forEach((node) => {
      node.innerHTML = icon(kind, value, label, src);
      markHost(node, kind, `${label}: ${stateText(value)}`);
    });
  }

  function indicatorLabel(lighting) {
    if (lighting.hazards === true) return "Hazard warning lights";
    if (lighting.left_indicator === true && lighting.right_indicator === true) return "Both direction indicators";
    if (lighting.left_indicator === true) return "Left direction indicator";
    if (lighting.right_indicator === true) return "Right direction indicator";
    if (lighting.left_indicator === false || lighting.right_indicator === false) return "Direction indicators off";
    return "Direction indicators unknown";
  }

  function setIndicators(lighting) {
    const hazards = lighting.hazards === true;
    const left = hazards ? true : lighting.left_indicator;
    const right = hazards ? true : lighting.right_indicator;
    const label = indicatorLabel(lighting);

    qsa('[data-field="indicators"]').forEach((node) => {
      node.innerHTML =
        `<span class="openmmi-indicator-pair ${hazards ? "is-hazard" : ""}">` +
          icon("left-turn", left, "Left direction indicator", ICONS.leftTurn) +
          icon("right-turn", right, "Right direction indicator", ICONS.rightTurn) +
        `</span>` + sr(label);
      markHost(node, "indicators", label);
    });
  }

  function applyInlineDataTelltales(payload) {
    const state = (payload && payload.state) || {};
    const vehicle = state.vehicle || {};
    const lighting = state.lighting || {};

    setIndicators(lighting);
    setNodeIcon('[data-bool="handbrake"]', "parking-brake", vehicle.handbrake, "Parking brake", ICONS.parkingBrake);
    setNodeIcon('[data-bool="hazards"]', "hazard", lighting.hazards, "Hazard warning", ICONS.hazard);
    setNodeIcon('[data-bool-no="bulb_out"]', "bulb-failure", lighting.bulb_out, "Exterior bulb failure", ICONS.bulbFailure);
  }

  if (typeof render !== "function") {
    console.warn("Open MMI tell-tale patch: render() was not found");
    return;
  }

  const previousRender = render;
  render = function renderWithInlineDataTelltales(payload) {
    previousRender(payload);
    applyInlineDataTelltales(payload || {});
  };

  window.openMmiApplyInlineDataTelltales = applyInlineDataTelltales;
})();
/* end open-mmi dashboard ui pass 11 */

/* open-mmi dashboard ui pass 12: coolant and voltage fixes */
(function installCoolantAndVoltageFixes() {
  "use strict";

  function qsa(selector) {
    return Array.from(document.querySelectorAll(selector));
  }

  function asNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function voltageState(voltage) {
    if (voltage === null) return "unknown";
    if (voltage < 11.8 || voltage > 15.2) return "danger";
    if (voltage < 12.2 || voltage > 14.9) return "warn";
    return "normal";
  }

  function coolantState(tempC) {
    if (tempC === null) return "unknown";
    if (tempC >= 112) return "hot";
    if (tempC <= 60) return "cold";
    return "normal";
  }

  function batterySvg() {
    return '' +
      '<svg class="openmmi-voltage-icon" viewBox="0 0 96 64" role="img" aria-hidden="true" focusable="false">' +
        '<path d="M18 18H78c4.4 0 8 3.6 8 8v12c4.4 0 8 3.6 8 8s-3.6 8-8 8v-2c0 4.4-3.6 8-8 8H18c-4.4 0-8-3.6-8-8V26c0-4.4 3.6-8 8-8Z" fill="none" stroke="currentColor" stroke-width="7" stroke-linejoin="round"/>' +
        '<path d="M31 32v14M24 39h14M61 39h14" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round"/>' +
      '</svg>';
  }

  function updateVoltageTellTale(payload) {
    const state = (payload && payload.state) || {};
    const electrical = state.electrical || {};
    const voltage = asNumber(electrical.supply_voltage_v ?? electrical.terminal30_voltage_v);
    const status = voltageState(voltage);

    qsa('[data-field="voltage_v"]').forEach((node) => {
      const text = node.textContent && node.textContent.trim() ? node.textContent.trim() : "--";
      node.classList.add("openmmi-voltage-field");
      node.innerHTML =
        '<span class="openmmi-voltage-readout is-' + status + '" title="Supply voltage: ' + text + ' V">' +
          batterySvg() +
          '<span class="openmmi-voltage-number">' + text + '</span>' +
        '</span>';

      const tile = node.closest('.tile');
      if (tile) {
        tile.classList.toggle('openmmi-voltage-warn', status === 'warn');
        tile.classList.toggle('openmmi-voltage-danger', status === 'danger');
      }
    });
  }

  function updateCoolantGauge(payload) {
    const state = (payload && payload.state) || {};
    const engine = state.engine || {};
    const tempC = asNumber(engine.coolant_temp_c);
    const status = coolantState(tempC);

    qsa('.temp-bar').forEach((bar) => {
      bar.classList.add('openmmi-coolant-gauge');
      bar.classList.remove('is-cold', 'is-normal', 'is-hot', 'is-unknown');
      bar.classList.add('is-' + status);

      if (tempC === null) {
        bar.style.removeProperty('--coolant-pos');
        bar.setAttribute('title', 'Coolant temperature: unknown');
        return;
      }

      // The printed scale is 50 / 90 / 130 °C, so map the marker to that range.
      const percent = clamp(((tempC - 50) / 80) * 100, 0, 100);
      bar.style.setProperty('--coolant-pos', percent.toFixed(1) + '%');
      bar.setAttribute('title', 'Coolant temperature: ' + openMmiFormatTempFromC(tempC, 0) + ' ' + openMmiTempUnitLabel());
    });
  }

  function applyCoolantAndVoltageFixes(payload) {
    updateVoltageTellTale(payload || {});
    updateCoolantGauge(payload || {});
  }

  if (typeof render !== "function") {
    console.warn("Open MMI coolant/voltage patch: render() was not found");
    return;
  }

  const previousRender = render;
  render = function renderWithCoolantAndVoltageFixes(payload) {
    previousRender(payload);
    applyCoolantAndVoltageFixes(payload || {});
  };

  window.openMmiApplyCoolantAndVoltageFixes = applyCoolantAndVoltageFixes;
})();
/* end open-mmi dashboard ui pass 12 */

function setPage(index) {
  activePage = (index + PAGE_IDS.length) % PAGE_IDS.length;
  PAGE_IDS.forEach((id, idx) => $("#" + id).classList.toggle("active", idx === activePage));
  $$(".pager button").forEach((button, idx) => button.classList.toggle("active", idx === activePage));
  $("#pageTitle").textContent = PAGE_NAMES[activePage];
}

function init() {
  $$(".pager button").forEach((button) => button.addEventListener("click", () => setPage(Number(button.dataset.page))));
  window.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") setPage(activePage + 1);
    if (event.key === "ArrowLeft") setPage(activePage - 1);
  });
  setPage(0);

  const statusPoller = openMmiStatusClient.createPoller({
    api: openMmiApiClient,
    store: openMmiStatusStore,
    intervalMs: openMmiStatusClient.DEFAULT_STATUS_INTERVAL_MS,
    onPayload(payload) { render(payload); },
    onError() { updateHealth({ health: { status: "error", age_seconds: null } }); },
  });
  window.openMmiStatusPoller = statusPoller;
  statusPoller.start();
}

init();


// --- Open MMI Jellyfin real Bootstrap media v5 start ---
/*
  Jellyfin Media v5
  - actual Bootstrap classes for layout: container-fluid/row/col/card/d-flex/overflow/list-group/input-group/btn/progress
  - Bootstrap Icons-style inline SVG controls, so controls are icons again and do not rely on icon font loading
  - measured viewport height so the Media page fits above the dashboard footer/status strip
  - local browser audio is primary; remote Jellyfin Web session is secondary status only
*/
try {
  if (Array.isArray(PAGE_NAMES)) PAGE_NAMES[3] = "Media";
  if (Array.isArray(PAGE_IDS)) PAGE_IDS[3] = "pageElectrical";
} catch (_) {}

const openMmiMedia = {
  queue: [],
  index: -1,
  current: null,
  bound: false,
  lastQuery: "",
  filter: "recent",
  loading: false,
};

function ommiMediaEsc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function ommiMediaText(value, fallback = "--") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function ommiMediaTime(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n) || n < 0) return "--:--";
  const total = Math.floor(n);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

function ommiMediaIcon(name, cls = "") {
  // Bootstrap Icons SVG paths, embedded inline so the controls work offline after the page loads.
  const paths = {
    "play-fill": '<path d="m11.596 8.697-6.363 3.692C4.693 12.702 4 12.323 4 11.692V4.308c0-.631.693-1.01 1.233-.697l6.363 3.692a.802.802 0 0 1 0 1.394z"/>',
    "pause-fill": '<path d="M5.5 3.5A1.5 1.5 0 0 1 7 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5zm5 0A1.5 1.5 0 0 1 12 5v6a1.5 1.5 0 0 1-3 0V5a1.5 1.5 0 0 1 1.5-1.5z"/>',
    "skip-start-fill": '<path d="M4 4a.5.5 0 0 1 1 0v3.248l6.267-3.636c.54-.313 1.233.066 1.233.696v7.384c0 .63-.693 1.009-1.233.696L5 8.752V12a.5.5 0 0 1-1 0V4z"/>',
    "skip-end-fill": '<path d="M12.5 4a.5.5 0 0 0-1 0v3.248L5.233 3.612C4.693 3.299 4 3.678 4 4.308v7.384c0 .63.693 1.009 1.233.696L11.5 8.752V12a.5.5 0 0 0 1 0V4z"/>',
    "stop-fill": '<path d="M5 3.5h6A1.5 1.5 0 0 1 12.5 5v6A1.5 1.5 0 0 1 11 12.5H5A1.5 1.5 0 0 1 3.5 11V5A1.5 1.5 0 0 1 5 3.5z"/>',
    "search": '<path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>',
    "clock-history": '<path d="M8.515 1.019A7 7 0 1 1 1.004 8.5.5.5 0 0 1 2 8a6 6 0 1 0 1.76-4.243l-.04.04h1.533a.5.5 0 0 1 0 1H2.5a.5.5 0 0 1-.5-.5V1.543a.5.5 0 0 1 1 0v1.52A6.974 6.974 0 0 1 8.515 1.019z"/><path d="M7.5 3a.5.5 0 0 1 .5.5v5.21l3.248 1.856a.5.5 0 0 1-.496.868l-3.5-2A.5.5 0 0 1 7 9V3.5a.5.5 0 0 1 .5-.5z"/>',
    "music-note-beamed": '<path d="M6 13c0 1.105-1.12 2-2.5 2S1 14.105 1 13s1.12-2 2.5-2 2.5.895 2.5 2z"/><path fill-rule="evenodd" d="M11 11V2h1v9h-1z"/><path d="M11 11c0 1.105-1.12 2-2.5 2S6 12.105 6 11s1.12-2 2.5-2 2.5.895 2.5 2z"/><path fill-rule="evenodd" d="M6 3v10H5V3h1z"/><path d="M5 2.905a1 1 0 0 1 .9-.995l6-.6a1 1 0 0 1 1.1.995V4L5 4.905v-2z"/>',
    "volume-up-fill": '<path d="M11.536 14.01A8.473 8.473 0 0 0 14.026 8a8.473 8.473 0 0 0-2.49-6.01l-.708.707A7.476 7.476 0 0 1 13.025 8c0 2.071-.84 3.946-2.197 5.303l.708.707z"/><path d="M10.121 12.596A6.48 6.48 0 0 0 12.025 8a6.48 6.48 0 0 0-1.904-4.596l-.707.707A5.48 5.48 0 0 1 11.025 8a5.48 5.48 0 0 1-1.61 3.89l.706.706z"/><path d="M8.707 11.182A4.486 4.486 0 0 0 10.025 8a4.486 4.486 0 0 0-1.318-3.182L8 5.525A3.489 3.489 0 0 1 9.025 8 3.49 3.49 0 0 1 8 10.475l.707.707zM6.717 3.55A.5.5 0 0 1 7 4v8a.5.5 0 0 1-.812.39L3.825 10.5H1.5A.5.5 0 0 1 1 10V6a.5.5 0 0 1 .5-.5h2.325l2.363-1.89a.5.5 0 0 1 .529-.06z"/>',
  };
  return `<svg class="bi ${cls}" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true" focusable="false">${paths[name] || paths["music-note-beamed"]}</svg>`;
}

// --- Open MMI Media icon/live search follow-up start ---
const OMMI_MEDIA_LIVE_SEARCH_DELAY_MS = 320;

function ommiMediaCleanMusicIcon(cls = "") {
  // A speaker silhouette is deliberately used instead of a note, disc, or
  // rounded-square/circle combination, which can resemble a social-media logo.
  const className = ["ommi-music-icon", "ommi-media-speaker-icon", cls]
    .filter(Boolean)
    .join(" ");
  return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M4.5 9.25h3.2l4.55-3.45v12.4L7.7 14.75H4.5z"
      fill="currentColor"/>
    <path d="M15.15 9.35c1.45 1.45 1.45 3.85 0 5.3"
      fill="none" stroke="currentColor" stroke-width="1.65"
      stroke-linecap="round"/>
    <path d="M17.7 7.15c2.75 2.75 2.75 6.95 0 9.7"
      fill="none" stroke="currentColor" stroke-width="1.65"
      stroke-linecap="round"/>
  </svg>`;
}

function ommiMediaInvalidateRequest() {
  openMmiMedia.requestSerial = (Number(openMmiMedia.requestSerial) || 0) + 1;
  ommiMediaSetLoading(false);
}

function ommiMediaRunSearchNow(value) {
  if (openMmiMedia.searchTimer) {
    clearTimeout(openMmiMedia.searchTimer);
    openMmiMedia.searchTimer = null;
  }
  return ommiMediaLoadLibrary(value || "", openMmiMedia.filter);
}

function ommiMediaScheduleLiveSearch(input) {
  if (openMmiMedia.searchTimer) clearTimeout(openMmiMedia.searchTimer);
  ommiMediaInvalidateRequest();
  const value = input?.value || "";
  openMmiMedia.searchTimer = setTimeout(() => {
    openMmiMedia.searchTimer = null;
    ommiMediaLoadLibrary(value, openMmiMedia.filter);
  }, OMMI_MEDIA_LIVE_SEARCH_DELAY_MS);
}

function ommiMediaBindLiveSearch(root) {
  const input = root?.querySelector?.("#ommiMediaSearch");
  if (!input || input.dataset.openMmiLiveSearchBound === "true") return;

  input.dataset.openMmiLiveSearchBound = "true";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = "Search music…";
  input.setAttribute("aria-label", "Search music; results update as you type");

  let composing = false;
  input.addEventListener("compositionstart", () => { composing = true; });
  input.addEventListener("compositionend", () => {
    composing = false;
    ommiMediaScheduleLiveSearch(input);
  });
  input.addEventListener("input", () => {
    if (!composing) ommiMediaScheduleLiveSearch(input);
  });
  input.addEventListener("keydown", (event) => {
    // Keep dashboard-wide shortcuts (H/Home and page arrows) out of text entry.
    // Native cursor movement is preserved; Enter remains an immediate search.
    event.stopPropagation();
    if (event.key === "Enter") {
      event.preventDefault();
      ommiMediaRunSearchNow(input.value || "");
    }
  });
  input.addEventListener("search", () => ommiMediaRunSearchNow(input.value || ""));
}
// --- Open MMI Media icon/live search follow-up end ---

function ommiMediaPage() {
  let page = document.querySelector("#pageElectrical") || Array.from(document.querySelectorAll(".page"))[3];
  if (!page) {
    page = document.createElement("section");
    const footer = document.querySelector("footer.status-strip") || document.querySelector("footer");
    (footer?.parentNode || document.body).insertBefore(page, footer || null);
  }
  const active = page.classList.contains("active");
  page.id = "pageElectrical";
  page.className = `page page-media${active ? " active" : ""}`;
  page.setAttribute("aria-label", "Media page");

  document.querySelectorAll(".media-shell, .open-mmi-media-v2, .open-mmi-media-v3, .open-mmi-media-v4, .open-mmi-media-v5").forEach((node) => {
    if (!page.contains(node)) node.remove();
  });

  if (!page.querySelector("#openMmiMediaRoot")) {
    page.replaceChildren(ommiMediaBuildRoot());
    openMmiMedia.bound = false;
  }
  ommiMediaUpdatePagerLabels();
  ommiMediaInstallFilters();
  ommiMediaBind();
  if (window.openMmiMediaSources) window.openMmiMediaSources.apply();
  ommiMediaFitViewport();
  return page;
}

function ommiMediaBuildRoot() {
  const root = document.createElement("div");
  root.id = "openMmiMediaRoot";
  root.dataset.bootstrap = "true";
  root.className = "open-mmi-media-v5 container-fluid p-0 overflow-hidden";
  root.innerHTML = `
    <div class="row gx-2 gy-0 h-100 min-h-0 overflow-hidden ommi-media-row align-items-stretch">
      <section class="col-12 col-md-5 col-xl-4 h-100 min-h-0 d-flex overflow-hidden ommi-player-col" aria-label="Local Jellyfin player">
        <div class="card flex-fill h-100 min-h-0 overflow-hidden ommi-media-card">
          <div class="card-body d-flex flex-column min-h-0 h-100 gap-2 ommi-player-body">
            <div id="ommiMediaArt" class="ommi-art flex-shrink-0" aria-hidden="true"><span>${ommiMediaCleanMusicIcon("ommi-art-icon")}</span></div>
            <div class="min-w-0 flex-shrink-0 ommi-now-copy">
              <div class="text-uppercase small text-secondary ommi-kicker">${ommiMediaIcon("volume-up-fill")} Local player</div>
              <h2 id="ommiMediaTitle" class="ommi-now-title mb-1">Select music</h2>
              <div id="ommiMediaSubtitle" class="ommi-now-subtitle text-secondary">Tap a track to play through this dashboard</div>
              <div id="ommiMediaMessage" class="ommi-message text-secondary" role="status"></div>
            </div>
            <audio id="ommiMediaAudio" preload="metadata"></audio>
            <div id="ommiMediaProgressTrack" class="progress ommi-progress flex-shrink-0" role="slider" aria-label="Playback progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
              <div id="ommiMediaProgressFill" class="progress-bar ommi-progress-fill" style="width:0%"></div>
            </div>
            <div class="d-flex justify-content-between small text-secondary ommi-time flex-shrink-0">
              <span id="ommiMediaElapsed">--:--</span><span id="ommiMediaDuration">--:--</span>
            </div>
            <div class="btn-group w-100 flex-shrink-0 ommi-controls" role="group" aria-label="Playback controls">
              <button type="button" id="ommiMediaPrev" class="btn btn-outline-light ommi-icon-btn" aria-label="Previous track">${ommiMediaIcon("skip-start-fill")}</button>
              <button type="button" id="ommiMediaPlay" class="btn btn-info ommi-icon-btn ommi-play-btn" aria-label="Play">${ommiMediaIcon("play-fill")}</button>
              <button type="button" id="ommiMediaNext" class="btn btn-outline-light ommi-icon-btn" aria-label="Next track">${ommiMediaIcon("skip-end-fill")}</button>
              <button type="button" id="ommiMediaStop" class="btn btn-outline-secondary ommi-icon-btn" aria-label="Stop">${ommiMediaIcon("stop-fill")}</button>
            </div>
          </div>
        </div>
      </section>

      <section class="col-12 col-md-7 col-xl-8 h-100 min-h-0 d-flex overflow-hidden ommi-browser-col" aria-label="Jellyfin music browser">
        <div class="card flex-fill h-100 min-h-0 overflow-hidden ommi-media-card">
          <div class="card-body d-flex flex-column min-h-0 h-100 gap-2 ommi-browser-body">
            <div class="input-group input-group-lg flex-shrink-0 ommi-search">
              <input id="ommiMediaSearch" type="search" class="form-control" autocomplete="off" placeholder="Search songs, artists, albums" aria-label="Search Jellyfin music">
              <button type="button" id="ommiMediaSearchBtn" class="btn btn-outline-light ommi-search-btn" aria-label="Search">${ommiMediaIcon("search")}</button>
              <button type="button" id="ommiMediaRecentBtn" class="btn btn-outline-secondary ommi-recent-btn" aria-label="Recent music">${ommiMediaIcon("clock-history")}</button>
            </div>
            <div class="d-flex justify-content-between align-items-center flex-shrink-0 ommi-list-heading">
              <span id="ommiMediaListTitle">Recent music</span>
              <span class="d-inline-flex align-items-center gap-2"><small id="ommiMediaRemoteState" class="text-secondary ommi-remote-state">--</small><span id="ommiMediaCount" class="badge rounded-pill text-bg-secondary">--</span></span>
            </div>
            <div id="ommiMediaResults" class="list-group list-group-flush flex-grow-1 min-h-0 overflow-auto ommi-results" role="list" aria-label="Tracks"></div>
          </div>
        </div>
      </section>
    </div>`;
  return root;
}

function ommiMediaFitViewport() {
  const page = document.querySelector("#pageElectrical.page-media");
  const root = document.querySelector("#openMmiMediaRoot");
  if (!page || !root) return;

  const pageRect = page.getBoundingClientRect();
  let bottom = window.innerHeight;
  const candidates = Array.from(document.querySelectorAll("footer, .footer, .status-strip, .nav-dots, .pager, .page-dots, .dashboard-footer, .bottom-bar"));
  for (const el of candidates) {
    if (page.contains(el) || !el.getClientRects().length) continue;
    const rect = el.getBoundingClientRect();
    if (rect.top > pageRect.top + 20 && rect.top < bottom) bottom = rect.top;
  }

  const safeGap = 8;
  const height = Math.max(220, Math.floor(bottom - pageRect.top - safeGap));
  root.style.height = `${height}px`;
  root.style.maxHeight = `${height}px`;
  root.style.minHeight = "0";
}

function ommiMediaUpdatePagerLabels() {
  document.querySelectorAll('[data-page="3"]').forEach((button) => {
    button.title = "Media";
    button.setAttribute("aria-label", "Media");
  });
  if (document.querySelector('[data-page="3"].active')) {
    const title = document.querySelector("#pageTitle");
    if (title) title.textContent = "Media";
  }
}

function ommiMediaSetMessage(text, kind = "") {
  const el = document.querySelector("#ommiMediaMessage");
  if (!el) return;
  el.textContent = text || "";
  el.className = `ommi-message ${kind === "error" ? "text-danger" : "text-secondary"}`;
}

function ommiMediaSetArtwork(track) {
  const art = document.querySelector("#ommiMediaArt");
  if (!art) return;
  if (track?.image_url) {
    art.classList.add("has-art");
    art.innerHTML = `<img src="${ommiMediaEsc(track.image_url)}" alt="">`;
  } else {
    art.classList.remove("has-art");
    art.innerHTML = `<span>${ommiMediaCleanMusicIcon("ommi-art-icon")}</span>`;
  }
}

function ommiMediaSetNowPlaying(track) {
  const title = document.querySelector("#ommiMediaTitle");
  const subtitle = document.querySelector("#ommiMediaSubtitle");
  if (!title || !subtitle) return;
  if (!track) {
    title.textContent = "Select music";
    subtitle.textContent = "Tap a track to play through this dashboard";
    ommiMediaSetArtwork(null);
    return;
  }
  title.textContent = ommiMediaText(track.name, "Untitled");
  subtitle.textContent = [track.artist, track.album].filter(Boolean).join(" · ") || "Jellyfin music";
  ommiMediaSetArtwork(track);
}

function ommiMediaUpdateProgress() {
  const audio = document.querySelector("#ommiMediaAudio");
  const elapsed = document.querySelector("#ommiMediaElapsed");
  const duration = document.querySelector("#ommiMediaDuration");
  const fill = document.querySelector("#ommiMediaProgressFill");
  const track = document.querySelector("#ommiMediaProgressTrack");
  if (!audio || !elapsed || !duration || !fill) return;
  const dur = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : Number(openMmiMedia.current?.duration_seconds || 0);
  const pct = dur > 0 ? Math.max(0, Math.min(100, (audio.currentTime / dur) * 100)) : 0;
  elapsed.textContent = ommiMediaTime(audio.currentTime);
  duration.textContent = ommiMediaTime(dur);
  fill.style.width = `${pct}%`;
  track?.setAttribute("aria-valuenow", String(Math.round(pct)));
}

function ommiMediaUpdatePlayState() {
  const audio = document.querySelector("#ommiMediaAudio");
  const play = document.querySelector("#ommiMediaPlay");
  if (play && audio) {
    play.innerHTML = audio.paused ? ommiMediaIcon("play-fill") : ommiMediaIcon("pause-fill");
    play.setAttribute("aria-label", audio.paused ? "Play" : "Pause");
  }
}

async function ommiMediaFetchJson(path) {
  return openMmiApiClient.getJson(path);
}

const OMMI_MEDIA_FILTERS = {
  recent: "Recent music",
  favorites: "Favourites",
  az: "A–Z",
};

function ommiMediaUpdateFilters() {
  const select = document.querySelector("#ommiMediaFilter");
  if (select && select.value !== openMmiMedia.filter) {
    select.value = openMmiMedia.filter;
  }
}

function ommiMediaInstallFilters() {
  let select = document.querySelector("#ommiMediaFilter");
  const recent = document.querySelector("#ommiMediaRecentBtn");

  if (!select && recent) {
    select = document.createElement("select");
    select.id = "ommiMediaFilter";
    select.className = "form-select ommi-filter-select";
    select.setAttribute("aria-label", "Music library view");
    select.title = "Choose music library view";

    Object.entries(OMMI_MEDIA_FILTERS).forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });

    select.addEventListener("change", () => {
      const input = document.querySelector("#ommiMediaSearch");
      if (input) input.value = "";
      openMmiMedia.filter = select.value || "recent";
      ommiMediaRunSearchNow("");
    });
    recent.replaceWith(select);
  }

  // Remove the previous button implementation when upgrading an already-patched UI.
  document.querySelectorAll("[data-open-mmi-filter]").forEach((button) => button.remove());

  const search = document.querySelector("#ommiMediaSearchBtn");
  if (search) {
    search.title = "Search music";
    search.setAttribute("aria-label", "Search music");
  }
  ommiMediaUpdateFilters();
}

function ommiMediaSetLoading(loading) {
  openMmiMedia.loading = Boolean(loading);
  const root = document.querySelector("#openMmiMediaRoot");
  root?.setAttribute("aria-busy", String(openMmiMedia.loading));
  document
    .querySelectorAll("#ommiMediaSearchBtn, #ommiMediaFilter")
    .forEach((control) => {
      control.disabled = openMmiMedia.loading;
    });
}

function ommiMediaRenderResults(items) {
  const results = document.querySelector("#ommiMediaResults");
  const count = document.querySelector("#ommiMediaCount");
  if (!results) return;

  openMmiMedia.queue = Array.isArray(items) ? items.filter((item) => item && item.id) : [];
  if (count) count.textContent = String(openMmiMedia.queue.length);

  if (!openMmiMedia.queue.length) {
    results.innerHTML = `<div class="ommi-empty">No tracks found. Try search, or check <code>/api/jellyfin/search?limit=5</code>.</div>`;
    return;
  }

  results.innerHTML = openMmiMedia.queue.map((item, index) => `
    <button type="button" class="list-group-item list-group-item-action d-grid ommi-track" data-open-mmi-track="${index}" role="listitem" aria-label="Play ${ommiMediaEsc(item.name || "track")}">
      <span class="ommi-track-art">${item.image_url ? `<img src="${ommiMediaEsc(item.image_url)}" alt="">` : ommiMediaCleanMusicIcon()}</span>
      <span class="ommi-track-copy"><strong>${ommiMediaEsc(item.name || "Untitled")}</strong><small>${ommiMediaEsc([item.artist, item.album].filter(Boolean).join(" · ") || "Unknown artist")}</small></span>
      <span class="ommi-track-duration">${ommiMediaTime(item.duration_seconds)}</span>
    </button>`).join("");
}

async function ommiMediaLoadLibrary(query = "", filter = openMmiMedia.filter) {
  ommiMediaPage();
  ommiMediaInstallFilters();
  if (window.openMmiMediaSources && !window.openMmiMediaSources.shouldUseJellyfin()) {
    window.openMmiMediaSources.renderPlaceholder();
    return;
  }
  const listTitle = document.querySelector("#ommiMediaListTitle");
  const q = String(query || "").trim();
  const selectedFilter = Object.prototype.hasOwnProperty.call(OMMI_MEDIA_FILTERS, filter)
    ? filter
    : "recent";
  const requestSerial = (Number(openMmiMedia.requestSerial) || 0) + 1;
  openMmiMedia.requestSerial = requestSerial;
  openMmiMedia.lastQuery = q;
  openMmiMedia.filter = selectedFilter;
  ommiMediaUpdateFilters();
  if (listTitle) {
    listTitle.textContent = q
      ? `Search results · ${OMMI_MEDIA_FILTERS[selectedFilter]}`
      : OMMI_MEDIA_FILTERS[selectedFilter];
  }
  ommiMediaSetMessage(q ? "Searching…" : `Loading ${OMMI_MEDIA_FILTERS[selectedFilter].toLowerCase()}…`);
  ommiMediaSetLoading(true);
  try {
    const params = new URLSearchParams({
      q,
      limit: "60",
      filter: selectedFilter,
    });
    const payload = await ommiMediaFetchJson(`/api/jellyfin/search?${params}`);
    if (requestSerial !== openMmiMedia.requestSerial) return;
    if (payload.error) ommiMediaSetMessage(payload.error, "error");
    else ommiMediaSetMessage("Tap any track to play locally.");
    ommiMediaRenderResults(payload.items || []);
  } catch (err) {
    if (requestSerial !== openMmiMedia.requestSerial) return;
    ommiMediaSetMessage(`Could not load library: ${err.message}`, "error");
    ommiMediaRenderResults([]);
  } finally {
    if (requestSerial === openMmiMedia.requestSerial) ommiMediaSetLoading(false);
  }
  if (requestSerial === openMmiMedia.requestSerial) ommiMediaFitViewport();
}

async function ommiMediaRefreshStatus() {
  ommiMediaPage();
  if (window.openMmiMediaSources && !window.openMmiMediaSources.shouldUseJellyfin()) { window.openMmiMediaSources.renderPlaceholder(); return; }
  try {
    const status = await ommiMediaFetchJson("/api/jellyfin/status");
    const remote = document.querySelector("#ommiMediaRemoteState");
    if (remote) {
      const label = status?.configured ? (status?.state_label || status?.status || "ready") : "not configured";
      remote.textContent = String(label).toUpperCase();
      remote.title = status?.subtitle || "";
    }
    if (!status?.configured) ommiMediaSetMessage(status.subtitle || "Jellyfin is not configured", "error");
  } catch (err) {
    const remote = document.querySelector("#ommiMediaRemoteState");
    if (remote) remote.textContent = "ERROR";
    ommiMediaSetMessage(`Jellyfin status failed: ${err.message}`, "error");
  }
}

async function ommiMediaPlayIndex(index) {
  ommiMediaPage();
  if (window.openMmiMediaSources && !window.openMmiMediaSources.shouldUseJellyfin()) { window.openMmiMediaSources.renderPlaceholder(); return; }
  const audio = document.querySelector("#ommiMediaAudio");
  const item = openMmiMedia.queue[Number(index)];
  if (!audio || !item) return;

  openMmiMedia.index = Number(index);
  openMmiMedia.current = item;
  ommiMediaSetNowPlaying(item);
  ommiMediaSetMessage("Loading audio…");

  document.querySelectorAll(".ommi-track.is-playing").forEach((node) => node.classList.remove("is-playing", "active"));
  document.querySelector(`[data-open-mmi-track="${openMmiMedia.index}"]`)?.classList.add("is-playing", "active");

  audio.src = `/api/jellyfin/stream/${encodeURIComponent(item.id)}`;
  audio.load();
  try {
    await audio.play();
    ommiMediaSetMessage("Playing locally on this dashboard.");
  } catch (err) {
    ommiMediaSetMessage(`Tap play to start audio: ${err.message}`, "error");
  }
  ommiMediaUpdatePlayState();
  ommiMediaFitViewport();
}

function ommiMediaNext() {
  if (!openMmiMedia.queue.length) return;
  const next = openMmiMedia.index < 0 ? 0 : (openMmiMedia.index + 1) % openMmiMedia.queue.length;
  ommiMediaPlayIndex(next);
}

function ommiMediaPrev() {
  if (!openMmiMedia.queue.length) return;
  const prev = openMmiMedia.index <= 0 ? openMmiMedia.queue.length - 1 : openMmiMedia.index - 1;
  ommiMediaPlayIndex(prev);
}

function ommiMediaBind() {
  if (openMmiMedia.bound) return;
  const root = document.querySelector("#openMmiMediaRoot");
  const audio = document.querySelector("#ommiMediaAudio");
  if (!root || !audio) return;
  ommiMediaBindLiveSearch(root);

  root.addEventListener("click", async (event) => {
    const trackButton = event.target.closest?.("[data-open-mmi-track]");
    if (trackButton) {
      event.preventDefault();
      await ommiMediaPlayIndex(trackButton.dataset.openMmiTrack);
      return;
    }
    if (event.target.closest?.("#ommiMediaSearchBtn")) {
      return ommiMediaRunSearchNow(
        document.querySelector("#ommiMediaSearch")?.value || "",
      );
    }
    if (event.target.closest?.("#ommiMediaPrev")) return ommiMediaPrev();
    if (event.target.closest?.("#ommiMediaNext")) return ommiMediaNext();
    if (event.target.closest?.("#ommiMediaStop")) {
      audio.pause();
      audio.currentTime = 0;
      openMmiMedia.current = null;
      openMmiMedia.index = -1;
      ommiMediaSetNowPlaying(null);
      document.querySelectorAll(".ommi-track.is-playing").forEach((node) => node.classList.remove("is-playing", "active"));
      ommiMediaUpdateProgress();
      ommiMediaUpdatePlayState();
      ommiMediaSetMessage("Stopped.");
      return;
    }
    if (event.target.closest?.("#ommiMediaPlay")) {
      if (!openMmiMedia.current && openMmiMedia.queue.length) return ommiMediaPlayIndex(0);
      if (audio.paused) {
        try { await audio.play(); ommiMediaSetMessage("Playing locally on this dashboard."); }
        catch (err) { ommiMediaSetMessage(`Could not start audio: ${err.message}`, "error"); }
      } else {
        audio.pause();
      }
      ommiMediaUpdatePlayState();
      return;
    }
    const progress = event.target.closest?.("#ommiMediaProgressTrack");
    if (progress && Number.isFinite(audio.duration) && audio.duration > 0) {
      const rect = progress.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      audio.currentTime = ratio * audio.duration;
      ommiMediaUpdateProgress();
    }
  });

  root.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target?.id === "ommiMediaSearch") {
      event.preventDefault();
      ommiMediaRunSearchNow(event.target.value || "");
    }
  });

  audio.addEventListener("timeupdate", ommiMediaUpdateProgress);
  audio.addEventListener("durationchange", ommiMediaUpdateProgress);
  audio.addEventListener("play", ommiMediaUpdatePlayState);
  audio.addEventListener("pause", ommiMediaUpdatePlayState);
  audio.addEventListener("ended", ommiMediaNext);
  audio.addEventListener("error", () => ommiMediaSetMessage("Audio stream failed. Check Jellyfin access and codec support.", "error"));

  window.addEventListener("resize", ommiMediaFitViewport);
  window.addEventListener("orientationchange", () => setTimeout(ommiMediaFitViewport, 100));
  openMmiMedia.bound = true;
}


// --- Open MMI media source shell v1 start ---
(function openMmiMediaSourceShellV1() {
  if (window.__openMmiMediaSourceShellV1Loaded) return;
  window.__openMmiMediaSourceShellV1Loaded = true;

  const STORE_KEY = "openmmi.dashboard.settings.v1";
  const SOURCES = [
    { id: "jellyfin", label: "Jellyfin", note: "Local library", planned: false },
    { id: "radio", label: "Internet radio", note: "Radio Browser stations", planned: false },
    { id: "usb", label: "USB", note: "read-only local media", planned: false },
    { id: "bluetooth", label: "Bluetooth", note: "connected phone playback controls", planned: false },
  ];

  const DEFAULT_MEDIA = {
    mediaActiveSource: "jellyfin",
    mediaDefaultSource: "jellyfin",
    mediaSources: {
      jellyfin: true,
      radio: false,
      usb: false,
      bluetooth: false,
    },
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const sourceById = (id) => SOURCES.find((source) => source.id === id) || SOURCES[0];

  function loadPrefs() {
    let saved = {};
    try { saved = openMmiPrefs.readObject(STORE_KEY, {}); }
    catch (_) { saved = {}; }
    const mediaSources = Object.assign({}, DEFAULT_MEDIA.mediaSources, saved.mediaSources || {});
    const prefs = Object.assign({}, DEFAULT_MEDIA, saved, { mediaSources });

    if (!sourceById(prefs.mediaDefaultSource)) prefs.mediaDefaultSource = "jellyfin";
    if (!sourceById(prefs.mediaActiveSource)) prefs.mediaActiveSource = prefs.mediaDefaultSource || "jellyfin";
    return prefs;
  }

  function savePrefs(prefs) {
    try { openMmiPrefs.writeJson(STORE_KEY, prefs); } catch (_) {}
    window.openMmiDashboardSettings = Object.assign({}, window.openMmiDashboardSettings || {}, prefs);
  }

  function isEnabled(id, prefs = loadPrefs()) {
    return prefs.mediaSources?.[id] === true;
  }

  function firstEnabled(prefs = loadPrefs()) {
    return SOURCES.find((source) => isEnabled(source.id, prefs))?.id || "";
  }

  function activeSourceId(prefs = loadPrefs()) {
    if (isEnabled(prefs.mediaActiveSource, prefs)) return prefs.mediaActiveSource;
    if (isEnabled(prefs.mediaDefaultSource, prefs)) return prefs.mediaDefaultSource;
    return firstEnabled(prefs);
  }

  function setSourceEnabled(id, enabled) {
    const prefs = loadPrefs();
    prefs.mediaSources[id] = !!enabled;

    if (!activeSourceId(prefs)) {
      const fallback = enabled ? id : firstEnabled(prefs);
      prefs.mediaActiveSource = fallback || id;
      prefs.mediaDefaultSource = fallback || prefs.mediaDefaultSource || id;
    } else if (!isEnabled(prefs.mediaActiveSource, prefs)) {
      prefs.mediaActiveSource = activeSourceId(prefs);
    }

    if (!isEnabled(prefs.mediaDefaultSource, prefs)) {
      prefs.mediaDefaultSource = activeSourceId(prefs) || prefs.mediaDefaultSource;
    }

    savePrefs(prefs);
    apply();
  }

  function setDefaultSource(id) {
    const prefs = loadPrefs();
    if (!isEnabled(id, prefs)) return;
    prefs.mediaDefaultSource = id;
    savePrefs(prefs);
    apply();
  }

  function setActiveSource(id) {
    const prefs = loadPrefs();
    if (!isEnabled(id, prefs)) return;
    prefs.mediaActiveSource = id;
    savePrefs(prefs);
    apply();

    if (id === "jellyfin") {
      try { if (typeof ommiMediaRefreshStatus === "function") ommiMediaRefreshStatus(); } catch (_) {}
      try {
        if (typeof ommiMediaLoadLibrary === "function" && (!window.openMmiMedia || !window.openMmiMedia.queue || !window.openMmiMedia.queue.length)) {
          ommiMediaLoadLibrary("");
        }
      } catch (_) {}
    }
  }

  function shouldUseJellyfin() {
    // Historical name retained for compatibility. The source shell should render
    // the real Media UI for every implemented source, not only Jellyfin.
    const prefs = loadPrefs();
    const active = activeSourceId(prefs);
    return ["jellyfin", "radio", "usb", "bluetooth"].includes(active) && isEnabled(active, prefs);
  }
  function renderSourceBar(root = $("#openMmiMediaRoot")) {
    if (!root) return;
    root.classList.add("openmmi-media-source-shell");
    let bar = root.querySelector("#openMmiMediaSourceBar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "openMmiMediaSourceBar";
      bar.className = "openmmi-media-source-bar";
      root.insertBefore(bar, root.firstChild);
    }

    const prefs = loadPrefs();
    const active = activeSourceId(prefs);
    const visibleSources = SOURCES.filter((source) => isEnabled(source.id, prefs));
    root.classList.toggle("openmmi-media-no-enabled-sources", visibleSources.length === 0);

    bar.innerHTML = visibleSources.map((source) => {
      const selected = source.id === active;
      const planned = source.planned ? '<span class="openmmi-media-source-planned">planned</span>' : '';
      return `
        <button type="button" class="openmmi-media-source-btn${selected ? " is-selected" : ""}" data-openmmi-media-source="${source.id}" aria-pressed="${selected ? "true" : "false"}" title="Switch media source">
          <span>${source.label}</span>${planned}
        </button>`;
    }).join("");
  }

  function renderPlaceholder() {
    const root = $("#openMmiMediaRoot");
    if (!root) return;
    renderSourceBar(root);

    if (shouldUseJellyfin()) {
      root.classList.remove("openmmi-media-source-placeholder-active");
      root.querySelector("#openMmiMediaSourcePlaceholder")?.remove();
      return;
    }

    const prefs = loadPrefs();
    const active = activeSourceId(prefs);
    const source = active ? sourceById(active) : null;
    root.classList.add("openmmi-media-source-placeholder-active");

    let placeholder = root.querySelector("#openMmiMediaSourcePlaceholder");
    if (!placeholder) {
      placeholder = document.createElement("section");
      placeholder.id = "openMmiMediaSourcePlaceholder";
      placeholder.className = "openmmi-media-source-placeholder";
      root.appendChild(placeholder);
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
    return settingsRow(
      source.label,
      source.planned ? `${source.note}; can be exposed as a placeholder source.` : source.id === "usb" ? "Read-only local media roots configured or discovered by the dashboard server." : source.id === "bluetooth" ? "Controls an already-connected Bluetooth media player through BlueZ; pairing stays in the operating system." : "Configured server-side with URL/token environment variables.",
      `<button type="button" class="openmmi-setting-pill${enabled ? "" : " is-selected"}" data-openmmi-media-source-enable="${source.id}" data-openmmi-media-source-value="off" aria-pressed="${enabled ? "false" : "true"}">off</button>` +
      `<button type="button" class="openmmi-setting-pill${enabled ? " is-selected" : ""}" data-openmmi-media-source-enable="${source.id}" data-openmmi-media-source-value="on" aria-pressed="${enabled ? "true" : "false"}">on</button>`
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
    const active = document.querySelector("[data-openmmi-settings-section].active")?.dataset?.openmmiSettingsSection;
    const panel = $("#openmmiSettingsPanel");
    if (active !== "media" || !panel) return;

    const prefs = loadPrefs();
    const activeId = activeSourceId(prefs);
    const activeLabel = activeId ? sourceById(activeId).label : "None";
    const defaultLabel = sourceById(prefs.mediaDefaultSource).label;

    panel.innerHTML = `
      <div data-openmmi-media-settings-panel="true">
        <div class="openmmi-settings-panel-head"><span>Media</span><small>sources</small></div>
        <div class="openmmi-settings-metric"><span>Active source</span><strong>${activeLabel}</strong></div>
        <div class="openmmi-settings-metric"><span>Default source</span><strong>${defaultLabel}</strong></div>
        ${settingsRow("Default source", "Used when the Media page opens or the active source is disabled.", defaultControls(prefs))}
        ${SOURCES.map((source) => sourceToggleRow(source, prefs)).join("")}
        ${settingsRow("Token privacy", "Jellyfin URL/token stay server-side. Source enablement is a browser-local dashboard preference.", '<button type="button" class="openmmi-setting-pill is-selected" disabled>locked</button>')}
        ${settingsRow("Media keys", "Browser/system media controls follow the currently selected source where supported.", '<button type="button" class="openmmi-setting-pill is-selected" disabled>active</button>')}
      </div>`;
  }

  function apply() {
    const root = $("#openMmiMediaRoot");
    if (root) {
      renderSourceBar(root);
      if (shouldUseJellyfin()) {
        root.classList.remove("openmmi-media-source-placeholder-active");
        root.querySelector("#openMmiMediaSourcePlaceholder")?.remove();
      } else {
        renderPlaceholder();
      }
    }
    renderSettingsPanel();
  }

  document.addEventListener("click", (event) => {
    const sourceButton = event.target.closest?.("[data-openmmi-media-source]");
    if (sourceButton) {
      setActiveSource(sourceButton.dataset.openmmiMediaSource);
      return;
    }

    const enableButton = event.target.closest?.("[data-openmmi-media-source-enable]");
    if (enableButton) {
      setSourceEnabled(enableButton.dataset.openmmiMediaSourceEnable, enableButton.dataset.openmmiMediaSourceValue === "on");
      return;
    }

    const defaultButton = event.target.closest?.("[data-openmmi-media-default-source]");
    if (defaultButton) {
      setDefaultSource(defaultButton.dataset.openmmiMediaDefaultSource);
      return;
    }

    if (event.target.closest?.('[data-openmmi-settings-section="media"]')) {
      requestAnimationFrame(renderSettingsPanel);
    }
  });

  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(apply));
  document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(apply));

  const observer = new MutationObserver(() => {
    const active = document.querySelector("[data-openmmi-settings-section].active")?.dataset?.openmmiSettingsSection;
    const panel = $("#openmmiSettingsPanel");
    if (active === "media" && panel && !panel.querySelector("[data-openmmi-media-settings-panel]")) {
      renderSettingsPanel();
    }
  });
  try { observer.observe(document.body, { childList: true, subtree: true }); } catch (_) {}

  window.openMmiMediaSources = {
    apply,
    activeSourceId,
    isEnabled,
    loadPrefs,
    renderPlaceholder,
    setActiveSource,
    shouldUseJellyfin,
  };
})();
// --- Open MMI media source shell v1 end ---

// --- Open MMI Internet Radio privacy consent start ---
(function openMmiRadioPrivacyConsent() {
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
})();
// --- Open MMI Internet Radio privacy consent end ---
// --- Open MMI media source adapters/radio start ---
(function openMmiMediaSourceAdaptersRadio() {
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

  function browserCountryCode() {
    try {
      const locale = new Intl.Locale(navigator.language || "");
      if (locale.region && /^[A-Za-z]{2}$/.test(locale.region)) return locale.region.toUpperCase();
    } catch (_) {}
    const match = String(navigator.language || "").match(/[-_]([A-Za-z]{2})$/);
    return match ? match[1].toUpperCase() : "";
  }

  function loadRadioFilterPrefs() {
    const stored = readStoredJson(RADIO_FILTER_PREFS_KEY, {});
    const hasStoredCountry = Object.prototype.hasOwnProperty.call(stored, "country");
    const storedCountry = String(stored.country || "");
    return {
      country: hasStoredCountry
        ? (/^[A-Za-z]{2}$/.test(storedCountry) ? storedCountry.toUpperCase() : "")
        : browserCountryCode(),
      language: String(stored.language || "").slice(0, 64),
    };
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
    const prefs = loadRadioFilterPrefs();
    const q = String(query || "").trim().toLocaleLowerCase();
    return Object.values(loadRadioFavorites())
      .filter((item) => {
        if (prefs.country && String(item.country_code || "").toUpperCase() !== prefs.country) {
          return false;
        }
        if (
          prefs.language
          && !String(item.language || "").toLocaleLowerCase().includes(prefs.language.toLocaleLowerCase())
        ) {
          return false;
        }
        if (!q) return true;
        return [item.name, item.artist, item.album, item.language]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase().includes(q));
      })
      .sort((left, right) => String(left.name).localeCompare(String(right.name)));
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
})();
// --- Open MMI media source adapters/radio end ---
function ommiMediaBoot() {
  ommiMediaPage();
  if (window.openMmiMediaSources && !window.openMmiMediaSources.shouldUseJellyfin()) { window.openMmiMediaSources.renderPlaceholder(); return; }
  ommiMediaSetNowPlaying(openMmiMedia.current);
  ommiMediaRefreshStatus();
  if (!openMmiMedia.queue.length) ommiMediaLoadLibrary("");
}

ommiMediaBoot();
document.addEventListener("DOMContentLoaded", ommiMediaBoot);
setInterval(() => { ommiMediaPage(); ommiMediaUpdatePagerLabels(); ommiMediaFitViewport(); }, 1000);
setInterval(ommiMediaRefreshStatus, 7000);
// --- Open MMI Jellyfin real Bootstrap media v5 end ---


// --- Open MMI Jellyfin viewport v6 start ---
/*
  Corrective viewport fit for the Media page.
  The previous Bootstrap pass measured the available height but then put a
  height:100% row with vertical gutters and full-height cards inside it, which
  caused the bottom of the player/card to be clipped. This wrapper replaces the
  fit function without touching the Jellyfin API/audio code.
*/
try {
  const ommiPreviousMediaFitViewport = typeof ommiMediaFitViewport === "function" ? ommiMediaFitViewport : null;
  ommiMediaFitViewport = function ommiMediaFitViewportV6() {
    const page = document.querySelector("#pageElectrical.page-media");
    const root = document.querySelector("#openMmiMediaRoot");
    if (!page || !root) {
      if (ommiPreviousMediaFitViewport) ommiPreviousMediaFitViewport();
      return;
    }

    const pageRect = page.getBoundingClientRect();
    let bottom = window.innerHeight;
    const selectors = [
      "footer", ".footer", ".status-strip", ".nav-dots", ".pager", ".page-dots",
      ".dashboard-footer", ".bottom-bar", ".footer-status", ".status-row"
    ].join(",");

    for (const el of Array.from(document.querySelectorAll(selectors))) {
      if (page.contains(el) || !el.getClientRects().length) continue;
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const rect = el.getBoundingClientRect();
      if (rect.top > pageRect.top + 16 && rect.top < bottom) bottom = rect.top;
    }

    // Leave enough gap for the page/card rounded corners to be visible instead
    // of ending exactly at the footer boundary and looking clipped.
    const safeGap = 14;
    const height = Math.max(220, Math.floor(bottom - pageRect.top - safeGap));
    page.style.setProperty("--ommi-media-viewport-height", `${height}px`);
    page.style.height = `${height}px`;
    page.style.maxHeight = `${height}px`;
    root.style.height = "100%";
    root.style.maxHeight = "100%";
    root.style.minHeight = "0";
  };

  window.addEventListener("resize", () => requestAnimationFrame(ommiMediaFitViewport));
  window.addEventListener("orientationchange", () => setTimeout(ommiMediaFitViewport, 150));
  requestAnimationFrame(ommiMediaFitViewport);
} catch (error) {
  console.warn("Open MMI Media viewport v6 failed", error);
}
// --- Open MMI Jellyfin viewport v6 end ---


// --- Open MMI Jellyfin render stability v8b start ---
/*
  Tolerant Media layout stabiliser.

  This patch intentionally avoids replacing the Jellyfin player functions; the
  current app.js has drifted through several small fixes, so exact function-name
  matching is fragile. Instead it stabilises the rendered Media DOM:
    - marks the active Media page/root with v8b classes,
    - reserves the track-list slot immediately with skeleton rows,
    - keeps page/root scroll at the top,
    - lets only #ommiMediaResults scroll,
    - reruns the existing viewport fit hook when the list mutates.
*/
(function () {
  const PAGE_SELECTOR = "#pageElectrical.page-media, #pageElectrical";
  const ROOT_SELECTOR = "#openMmiMediaRoot";
  const RESULTS_SELECTOR = "#ommiMediaResults";

  function fit() {
    const page = document.querySelector(PAGE_SELECTOR);
    const root = document.querySelector(ROOT_SELECTOR);
    const results = document.querySelector(RESULTS_SELECTOR);

    if (page) {
      page.classList.add("page-media-v8b");
      if (page.classList.contains("active")) page.scrollTop = 0;
    }
    if (root) {
      root.classList.add("open-mmi-media-v8b");
      root.scrollTop = 0;
    }
    if (results) {
      results.classList.add("ommi-results-v8b");
      if (!results.dataset.openMmiUserScrolled) results.scrollTop = 0;
    }

    if (typeof window.ommiMediaFitViewport === "function") {
      try { window.ommiMediaFitViewport(); } catch (_) {}
    } else if (typeof ommiMediaFitViewport === "function") {
      try { ommiMediaFitViewport(); } catch (_) {}
    }
  }

  function skeleton() {
    const results = document.querySelector(RESULTS_SELECTOR);
    if (!results) return;
    const hasRealRows = results.querySelector(".ommi-track:not(.ommi-track-skeleton-v8b), .list-group-item:not(.ommi-track-skeleton-v8b)");
    const hasChildren = results.children.length > 0;
    if (hasRealRows || hasChildren) return;

    results.dataset.openMmiState = "loading";
    results.innerHTML = Array.from({ length: 8 }, (_, index) => `
      <div class="ommi-track ommi-track-skeleton-v8b" aria-hidden="true">
        <span class="ommi-track-art ommi-skeleton-box-v8b"></span>
        <span class="ommi-track-copy">
          <strong class="ommi-skeleton-line-v8b ${index % 3 === 0 ? "is-short" : ""}"></strong>
          <small class="ommi-skeleton-line-v8b ${index % 2 === 0 ? "is-tiny" : ""}"></small>
        </span>
        <span class="ommi-track-duration ommi-skeleton-line-v8b is-time"></span>
      </div>`).join("");
  }

  function stabilise() {
    skeleton();
    fit();
    requestAnimationFrame(fit);
  }

  function bindResultsScroll() {
    const results = document.querySelector(RESULTS_SELECTOR);
    if (!results || results.__openMmiV8bScrollBound) return;
    results.addEventListener("scroll", () => {
      if (results.scrollTop > 8) results.dataset.openMmiUserScrolled = "1";
    }, { passive: true });
    results.__openMmiV8bScrollBound = true;
  }

  function observe() {
    const root = document.querySelector(ROOT_SELECTOR) || document.body;
    if (root.__openMmiV8bObserverBound) return;
    const observer = new MutationObserver(() => {
      bindResultsScroll();
      requestAnimationFrame(stabilise);
    });
    observer.observe(root, { childList: true, subtree: true });
    root.__openMmiV8bObserverBound = true;
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindResultsScroll();
    observe();
    stabilise();
    setTimeout(stabilise, 250);
    setTimeout(stabilise, 1000);
  });

  window.addEventListener("resize", () => requestAnimationFrame(stabilise));
  window.addEventListener("orientationchange", () => setTimeout(stabilise, 150));

  // If this script is appended after DOMContentLoaded, run immediately too.
  if (document.readyState !== "loading") {
    bindResultsScroll();
    observe();
    stabilise();
    setTimeout(stabilise, 250);
    setTimeout(stabilise, 1000);
  }
})();
// --- Open MMI Jellyfin render stability v8b end ---


// --- Open MMI media early footer guard start ---
/*
  Keep the Media page inside the content row immediately, before the Jellyfin
  library request completes. This avoids the brief first-paint overlap where the
  Media player can cover the bottom status/nav strip and then snap back.
*/
(function () {
  function clampMediaToContentRow() {
    const page = document.querySelector("#pageElectrical.page-media, #pageElectrical");
    const root = document.querySelector("#openMmiMediaRoot");
    const screen = document.querySelector(".screen");
    const footer = document.querySelector(".status-strip");
    if (!page || !screen) return;

    const screenRect = screen.getBoundingClientRect();
    const pageRect = page.getBoundingClientRect();
    const footerRect = footer ? footer.getBoundingClientRect() : null;
    const bottom = footerRect ? footerRect.top : screenRect.bottom;
    const available = Math.max(180, Math.floor(bottom - pageRect.top));

    page.style.height = `${available}px`;
    page.style.maxHeight = `${available}px`;
    page.style.minHeight = "0";
    page.style.overflow = "hidden";

    if (root) {
      root.style.height = "100%";
      root.style.maxHeight = "100%";
      root.style.minHeight = "0";
      root.style.overflow = "hidden";
    }

    const results = document.querySelector("#ommiMediaResults");
    if (results) {
      results.style.minHeight = "0";
      results.style.overflowY = "auto";
      results.style.overflowX = "hidden";
    }
  }

  function scheduleClamp() {
    clampMediaToContentRow();
    requestAnimationFrame(clampMediaToContentRow);
    setTimeout(clampMediaToContentRow, 80);
    setTimeout(clampMediaToContentRow, 300);
  }

  document.addEventListener("DOMContentLoaded", scheduleClamp);
  window.addEventListener("resize", scheduleClamp);
  window.addEventListener("orientationchange", () => setTimeout(scheduleClamp, 150));

  const observer = new MutationObserver(scheduleClamp);
  if (document.readyState !== "loading") scheduleClamp();
  document.addEventListener("DOMContentLoaded", () => {
    const target = document.querySelector("#pageElectrical") || document.body;
    observer.observe(target, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style"] });
  });
})();
// --- Open MMI media early footer guard end ---


// --- Open MMI media footer scoped repair start ---
/*
  Media-only footer clamp.

  The previous first-paint fix used global .screen/.page grid rules, which could
  break Drive/Climate/Vehicle. This repair measures the actual distance from the
  active Media page top to the status/footer strip and applies that height only
  to #pageElectrical.page-media and #openMmiMediaRoot.
*/
(function () {
  const PAGE_SELECTOR = "#pageElectrical.page-media, #pageElectrical";
  const ROOT_SELECTOR = "#openMmiMediaRoot";
  const FOOTER_SELECTOR = ".status-strip, footer.status-strip, .screen > footer";

  let raf = 0;

  function getMediaPage() {
    const page = document.querySelector(PAGE_SELECTOR);
    if (!page) return null;
    // Only clamp the Jellyfin/Media page. If the old id exists on a non-media
    // page, require the Media root to be present before changing dimensions.
    const root = page.querySelector(ROOT_SELECTOR) || document.querySelector(ROOT_SELECTOR);
    if (!root) return null;
    return { page, root };
  }

  function clearWhenInactive(page, root) {
    if (page.classList.contains("active")) return false;
    page.classList.remove("ommi-media-footer-scoped");
    page.style.removeProperty("--ommi-media-page-height");
    root.style.removeProperty("--ommi-media-root-height");
    return true;
  }

  function clampMediaFooter() {
    raf = 0;
    const media = getMediaPage();
    if (!media) return;
    const { page, root } = media;
    if (clearWhenInactive(page, root)) return;

    const footer = document.querySelector(FOOTER_SELECTOR);
    const screen = document.querySelector(".screen") || document.body;
    if (!footer || !screen) return;

    const pageRect = page.getBoundingClientRect();
    const footerRect = footer.getBoundingClientRect();
    const screenRect = screen.getBoundingClientRect();

    // Use the earlier of footer top and screen bottom, so the media root cannot
    // cover the footer even during Jellyfin/library first paint.
    const bottomLimit = Math.min(footerRect.top, screenRect.bottom);
    const available = Math.floor(bottomLimit - pageRect.top - 6);

    // Ignore impossible measurements during the earliest layout ticks; retry
    // shortly instead of writing nonsense dimensions.
    if (!Number.isFinite(available) || available < 180) {
      setTimeout(requestClamp, 40);
      return;
    }

    const px = `${available}px`;
    page.classList.add("ommi-media-footer-scoped");
    page.style.setProperty("--ommi-media-page-height", px);
    root.style.setProperty("--ommi-media-root-height", px);

    const results = document.querySelector("#ommiMediaResults");
    if (results) results.classList.add("ommi-media-results-scoped");
  }

  function requestClamp() {
    if (raf) return;
    raf = requestAnimationFrame(clampMediaFooter);
  }

  function scheduleStartupClamps() {
    requestClamp();
    requestAnimationFrame(requestClamp);
    setTimeout(requestClamp, 50);
    setTimeout(requestClamp, 200);
    setTimeout(requestClamp, 800);
  }

  document.addEventListener("DOMContentLoaded", scheduleStartupClamps);
  window.addEventListener("resize", requestClamp, { passive: true });
  window.addEventListener("orientationchange", () => setTimeout(requestClamp, 120), { passive: true });

  // Page changes and Jellyfin list loads can alter the active page/content.
  const observer = new MutationObserver(requestClamp);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style"]
    }));
  } else if (document.body) {
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style"]
    });
    scheduleStartupClamps();
  }

  window.openMmiClampMediaFooter = requestClamp;
})();
// --- Open MMI media footer scoped repair end ---


// --- Open MMI Jellyfin media keys fix start ---
/*
  System media-key integration for the local Jellyfin player.

  Browsers often handle play/pause automatically for an <audio> element, but
  next/previous track usually require Media Session action handlers. The helper
  functions below delegate to the existing Jellyfin player functions when they
  exist, and fall back to clicking the visible dashboard controls otherwise.
*/
(function () {
  const AUDIO_SELECTORS = ["#ommiMediaAudio", "#mediaAudio"];

  function mediaAudio() {
    for (const selector of AUDIO_SELECTORS) {
      const audio = document.querySelector(selector);
      if (audio) return audio;
    }
    return null;
  }

  function clickFirst(selectors) {
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        element.click();
        return true;
      }
    }
    return false;
  }

  function callIfFunction(name) {
    const fn = window[name] || (typeof globalThis !== "undefined" ? globalThis[name] : null);
    if (typeof fn === "function") {
      fn();
      return true;
    }
    return false;
  }

  function mediaNext() {
    if (callIfFunction("openMmiMediaNext")) return;
    if (callIfFunction("mediaNextTrack")) return;
    clickFirst(["#ommiMediaNext", "#mediaNext", '[aria-label="Next"]', '[aria-label="Next track"]']);
  }

  function mediaPrev() {
    if (callIfFunction("openMmiMediaPrev")) return;
    if (callIfFunction("mediaPreviousTrack")) return;
    clickFirst(["#ommiMediaPrev", "#mediaPrev", '[aria-label="Previous"]', '[aria-label="Previous track"]']);
  }

  async function mediaPlay() {
    const audio = mediaAudio();
    if (!audio) {
      clickFirst(["#ommiMediaPlay", "#mediaPlayPause", '[aria-label="Play or pause"]']);
      return;
    }
    try {
      if (audio.paused) await audio.play();
    } catch (_) {
      clickFirst(["#ommiMediaPlay", "#mediaPlayPause", '[aria-label="Play or pause"]']);
    }
  }

  function mediaPause() {
    const audio = mediaAudio();
    if (audio && !audio.paused) audio.pause();
  }

  function mediaPlayPause() {
    const audio = mediaAudio();
    if (!audio) {
      clickFirst(["#ommiMediaPlay", "#mediaPlayPause", '[aria-label="Play or pause"]']);
      return;
    }
    if (audio.paused) mediaPlay();
    else audio.pause();
  }

  function mediaStop() {
    const audio = mediaAudio();
    if (clickFirst(["#ommiMediaStop", "#mediaStop", '[aria-label="Stop"]'])) return;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
  }

  function updateMediaSessionMetadata() {
    if (!("mediaSession" in navigator) || !("MediaMetadata" in window)) return;

    const title = document.querySelector("#ommiMediaTitle, #mediaTitle")?.textContent?.trim() || "Open MMI";
    const subtitle = document.querySelector("#ommiMediaSubtitle, #mediaSubtitle")?.textContent?.trim() || "Jellyfin";
    const art = document.querySelector("#ommiMediaArt img, #mediaArt img, .ommi-track.is-playing img")?.src;

    const metadata = {
      title,
      artist: subtitle,
      album: "Open MMI",
    };

    if (art) {
      metadata.artwork = [
        { src: art, sizes: "96x96", type: "image/jpeg" },
        { src: art, sizes: "256x256", type: "image/jpeg" },
        { src: art, sizes: "512x512", type: "image/jpeg" },
      ];
    }

    try {
      navigator.mediaSession.metadata = new MediaMetadata(metadata);
    } catch (_) {
      // Metadata is nice-to-have; media-key handlers are the important part.
    }
  }

  function updateMediaSessionPlaybackState() {
    if (!("mediaSession" in navigator)) return;
    const audio = mediaAudio();
    try {
      navigator.mediaSession.playbackState = audio && !audio.paused ? "playing" : "paused";
    } catch (_) {}
  }

  function bindMediaSession() {
    if (!("mediaSession" in navigator)) return;

    const handlers = {
      play: mediaPlay,
      pause: mediaPause,
      stop: mediaStop,
      previoustrack: mediaPrev,
      nexttrack: mediaNext,
    };

    for (const [action, handler] of Object.entries(handlers)) {
      try {
        navigator.mediaSession.setActionHandler(action, handler);
      } catch (_) {
        // Some browsers omit specific actions; ignore unsupported ones.
      }
    }

    updateMediaSessionMetadata();
    updateMediaSessionPlaybackState();
  }

  function bindKeyboardMediaKeys() {
    if (window.__openMmiMediaKeyKeyboardBound) return;
    window.__openMmiMediaKeyKeyboardBound = true;

    document.addEventListener("keydown", (event) => {
      switch (event.key) {
        case "MediaTrackNext":
          event.preventDefault();
          mediaNext();
          break;
        case "MediaTrackPrevious":
          event.preventDefault();
          mediaPrev();
          break;
        case "MediaPlayPause":
          event.preventDefault();
          mediaPlayPause();
          break;
        case "MediaStop":
          event.preventDefault();
          mediaStop();
          break;
        default:
          break;
      }
    }, true);
  }

  function bindAudioEvents() {
    const audio = mediaAudio();
    if (!audio || audio.__openMmiMediaKeysBound) return;
    audio.__openMmiMediaKeysBound = true;

    for (const eventName of ["play", "pause", "ended", "loadedmetadata", "durationchange"]) {
      audio.addEventListener(eventName, () => {
        updateMediaSessionMetadata();
        updateMediaSessionPlaybackState();
      });
    }
  }

  function bootMediaKeys() {
    bindKeyboardMediaKeys();
    bindMediaSession();
    bindAudioEvents();
  }

  document.addEventListener("DOMContentLoaded", bootMediaKeys);
  if (document.readyState !== "loading") bootMediaKeys();

  // The Media page is created dynamically, so retry lightly until its audio
  // element exists. This is deliberately cheap and stops rebinding once bound.
  setInterval(bootMediaKeys, 1500);
})();
// --- Open MMI Jellyfin media keys fix end ---

// --- Open MMI proper light tell-tales start ---
(function installProperLightTelltales() {
  "use strict";

  const ICONS = Object.freeze({
    "leftTurn": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMTg1LjEyMzc1IgogICBoZWlnaHQ9IjIwNy45OTk5NSIKICAgaWQ9InN2ZzQzMjkiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC40OC40IHI5OTM5IgogICBzb2RpcG9kaTpkb2NuYW1lPSJBMTZMLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczQzMzEiIC8+CiAgPHNvZGlwb2RpOm5hbWVkdmlldwogICAgIGlkPSJiYXNlIgogICAgIHBhZ2Vjb2xvcj0iI2ZmZmZmZiIKICAgICBib3JkZXJjb2xvcj0iIzY2NjY2NiIKICAgICBib3JkZXJvcGFjaXR5PSIxLjAiCiAgICAgaW5rc2NhcGU6cGFnZW9wYWNpdHk9IjAuMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOnpvb209IjIuOCIKICAgICBpbmtzY2FwZTpjeD0iNjIuMTA3MzAxIgogICAgIGlua3NjYXBlOmN5PSI3Ni4yODI0ODMiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmN1cnJlbnQtbGF5ZXI9ImxheWVyMSIKICAgICBzaG93Z3JpZD0iZmFsc2UiCiAgICAgZml0LW1hcmdpbi10b3A9IjQiCiAgICAgZml0LW1hcmdpbi1sZWZ0PSI0IgogICAgIGZpdC1tYXJnaW4tcmlnaHQ9IjQiCiAgICAgZml0LW1hcmdpbi1ib3R0b209IjQiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIxOTIwIgogICAgIGlua3NjYXBlOndpbmRvdy1oZWlnaHQ9IjExNTMiCiAgICAgaW5rc2NhcGU6d2luZG93LXg9IjEyNzYiCiAgICAgaW5rc2NhcGU6d2luZG93LXk9Ii00IgogICAgIGlua3NjYXBlOndpbmRvdy1tYXhpbWl6ZWQ9IjEiIC8+CiAgPG1ldGFkYXRhCiAgICAgaWQ9Im1ldGFkYXRhNDMzNCI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgICA8ZGM6dGl0bGU+PC9kYzp0aXRsZT4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+CiAgPGcKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIgogICAgIGlkPSJsYXllcjEiCiAgICAgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTExNS42NTY0OCwtMzczLjA5NDQ1KSI+CiAgICA8ZwogICAgICAgaWQ9Imc1Mjk1IgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS45NDE3NDcxLDAsMCwxLjk0MTc0NzEsLTE2Mi42MjUsLTQ1NS40Mjk2MikiPgogICAgICA8cmVjdAogICAgICAgICB5PSI0MzAuMTMxMDQiCiAgICAgICAgIHg9IjE0Ni43NDcwMiIKICAgICAgICAgaGVpZ2h0PSIxMDAuMjY0OTUiCiAgICAgICAgIHdpZHRoPSI4OC40NzkyMSIKICAgICAgICAgaWQ9InJlY3Q1MjkzIgogICAgICAgICBzdHlsZT0iZmlsbDojMDBhMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjczNTA3MjE0O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzM1MSIKICAgICAgICAgZD0ibSAxNDcuNjYzODksNTA1LjkxMTY4IDAsLTIzLjg1MTkgMTUuNzY5MTUsMTUuNjAxOSBjIDguNjczMDMsOC41ODEgMTkuNDczMDMsMTkuMTM5NiAyNCwyMy40NjM2IDQuNTI2OTcsNC4zMjM5IDguMjMwODUsOC4wMzY0IDguMjMwODUsOC4yNSAwLDAuMjEzNSAtMTAuOCwwLjM4ODIgLTI0LDAuMzg4MiBsIC0yNCwwIDAsLTIzLjg1MTggeiBtIDUxLjgzNDA3LDEwLjYwMzIgYyAwLjE4Mzc0LC03LjI4ODMgMC40MTUzLC0xMy4zMzMgMC41MTQ1OCwtMTMuNDMyNiAwLjA5OTMsLTAuMSA3LjkzNzA0LC0wLjMyNDcgMTcuNDE3MjQsLTAuNSBsIDE3LjIzNjczLC0wLjMxODggLTEwZS00LDEzLjc1IC0wLjAwMSwxMy43NSAtMTcuNzUsMCAtMTcuNzUsMCAwLjMzNDA3LC0xMy4yNTE0IHogbSAtMjUuMzM5OTMsLTI0Ljc1NzMgLTEwLjk3MTc1LC0xMS4wMDU5IDExLjczODgxLC0xMS43Mzg4IDExLjczODgsLTExLjczODggMCw1LjE3MzMgYyAwLDguMTU2OSAwLjM3NDc4LDguMzE2MSAxOS41NzE0Myw4LjMxNjEgbCAxNi40Mjg1NywwIDAsMTAgMCwxMCAtMTYuNDI4NTcsMCBjIC0xOC44ODE2MywwIC0xOS41NzE0MywwLjI2NjkgLTE5LjU3MTQzLDcuNTcxNCAwLDIuNDM1NyAtMC4zNDUxNyw0LjQyODYgLTAuNzY3MDUsNC40Mjg2IC0wLjQyMTg4LDAgLTUuNzA0MzUsLTQuOTUyNiAtMTEuNzM4ODEsLTExLjAwNTkgeiBtIC0yNi40OTQxNCwtMzYuNTE3NiAwLC0yNC40NzY1IDI0LjQ3NjM5LDAgMjQuNDc2MzgsMCAtMTYuNDY5NCwxNi4xMzYzIGMgLTkuMDU4MTgsOC44NzQ5IC0yMC4wNzI1NSwxOS44ODk0IC0yNC40NzYzOSwyNC40NzY1IGwgLTguMDA2OTgsOC4zNDAzIDAsLTI0LjQ3NjYgeiBtIDY4Ljc1LDMuNzc1MiAtMTYuNzUsLTAuMzAwMSAwLC0xMi4zOTQgYyAwLC02LjgxNjcgLTAuMjczMTUsLTEzLjEwNTggLTAuNjA2OTksLTEzLjk3NTggLTAuNTM5NzIsLTEuNDA2NSAxLjM5OTY0LC0xLjU4MTggMTcuNSwtMS41ODE4IGwgMTguMTA2OTksMCAwLDE0LjUgYyAwLDcuOTc1IC0wLjMzNzUsMTQuMzk5MSAtMC43NSwxNC4yNzU5IC0wLjQxMjUsLTAuMTIzMyAtOC4yODc1LC0wLjM1OTIgLTE3LjUsLTAuNTI0MiB6IgogICAgICAgICBzdHlsZT0iZmlsbDojMDAwMDAwIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==",
    "rightTurn": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMTgzLjk2MDg5IgogICBoZWlnaHQ9IjIwNy45ODI4NSIKICAgaWQ9InN2ZzQzMjkiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC40OC40IHI5OTM5IgogICBzb2RpcG9kaTpkb2NuYW1lPSJBMTZSLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczQzMzEiIC8+CiAgPHNvZGlwb2RpOm5hbWVkdmlldwogICAgIGlkPSJiYXNlIgogICAgIHBhZ2Vjb2xvcj0iI2ZmZmZmZiIKICAgICBib3JkZXJjb2xvcj0iIzY2NjY2NiIKICAgICBib3JkZXJvcGFjaXR5PSIxLjAiCiAgICAgaW5rc2NhcGU6cGFnZW9wYWNpdHk9IjAuMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOnpvb209IjIuOCIKICAgICBpbmtzY2FwZTpjeD0iNjEuNTQ0OTAzIgogICAgIGlua3NjYXBlOmN5PSI3NS43MDk4NDkiCiAgICAgaW5rc2NhcGU6ZG9jdW1lbnQtdW5pdHM9InB4IgogICAgIGlua3NjYXBlOmN1cnJlbnQtbGF5ZXI9ImxheWVyMSIKICAgICBzaG93Z3JpZD0iZmFsc2UiCiAgICAgZml0LW1hcmdpbi10b3A9IjQiCiAgICAgZml0LW1hcmdpbi1sZWZ0PSI0IgogICAgIGZpdC1tYXJnaW4tcmlnaHQ9IjQiCiAgICAgZml0LW1hcmdpbi1ib3R0b209IjQiCiAgICAgaW5rc2NhcGU6d2luZG93LXdpZHRoPSIxOTIwIgogICAgIGlua3NjYXBlOndpbmRvdy1oZWlnaHQ9IjExNTMiCiAgICAgaW5rc2NhcGU6d2luZG93LXg9IjEyNzYiCiAgICAgaW5rc2NhcGU6d2luZG93LXk9Ii00IgogICAgIGlua3NjYXBlOndpbmRvdy1tYXhpbWl6ZWQ9IjEiIC8+CiAgPG1ldGFkYXRhCiAgICAgaWQ9Im1ldGFkYXRhNDMzNCI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgICA8ZGM6dGl0bGU+PC9kYzp0aXRsZT4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+CiAgPGcKICAgICBpbmtzY2FwZTpsYWJlbD0iTGF5ZXIgMSIKICAgICBpbmtzY2FwZTpncm91cG1vZGU9ImxheWVyIgogICAgIGlkPSJsYXllcjEiCiAgICAgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTExNi4yMTg4OCwtMzcyLjUzODkyKSI+CiAgICA8ZwogICAgICAgaWQ9Imc1MzE5IgogICAgICAgdHJhbnNmb3JtPSJtYXRyaXgoMS45MjE3NTcxLDAsMCwxLjkyMTc1NzEsLTE0NS44MjQzNywtNDQ2Ljk5NDA1KSI+CiAgICAgIDxyZWN0CiAgICAgICAgIHk9IjQyOS44NzMwMiIKICAgICAgICAgeD0iMTM5Ljc5MjI4IgogICAgICAgICBoZWlnaHQ9IjEwMS4zNzEyNyIKICAgICAgICAgd2lkdGg9Ijg4Ljg3MTI2OSIKICAgICAgICAgaWQ9InJlY3Q1MzE3IgogICAgICAgICBzdHlsZT0iZmlsbDojMDBhMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjcwMDE1NzE3O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzM0OSIKICAgICAgICAgZD0ibSAxNDAuNzI3OTEsNTE1Ljg4MDEyIDAsLTE0LjUgMTYuOCwwIGMgMTEuNzMzMzMsMCAxNy4xNjE5LDAuMzYxOSAxOCwxLjIgMC44MTMwMywwLjgxMyAxLjIsNS40ODg5IDEuMiwxNC41IGwgMCwxMy4zIC0xOCwwIC0xOCwwIDAsLTE0LjUgeiBtIDM3LjEwMDkxLDE0LjI1IGMgMC4yMzg4MywtMC4xMzc1IDExLjU2MzgzLC0xMS4yNjI4IDI1LjE2NjY2LC0yNC43MjI5IGwgMjQuNzMyNDMsLTI0LjQ3MjkgMCwyNC43MjI5IDAsMjQuNzIyOSAtMjUuMTY2NjcsMCBjIC0xMy44NDE2NiwwIC0yNC45NzEyNSwtMC4xMTI1IC0yNC43MzI0MiwtMC4yNSB6IG0gMTAuNTIwMTcsLTI5LjI5NTEgYyAtMC4zNDE1OSwtMC44OTAxIC0wLjYyMTA4LC0zLjM4MTcgLTAuNjIxMDgsLTUuNTM2NyBsIDAsLTMuOTE4MiAtMTYuOCwwIGMgLTExLjczMzMzLDAgLTE3LjE2MTkxLC0wLjM2MTkgLTE4LC0xLjIgLTEuNjIwNjksLTEuNjIwNyAtMS42MjA2OSwtMTcuOTc5MyAwLC0xOS42IDAuODM4MDksLTAuODM4MSA2LjI2NjY3LC0xLjIgMTgsLTEuMiBsIDE2LjgsMCAwLC00Ljk0MSBjIDAsLTIuNzE3NSAwLjM5MDU4LC01LjE4MjQgMC44Njc5NiwtNS40Nzc0IDAuNDc3MzgsLTAuMjk1IDUuOTUyNyw0LjMzMDIgMTIuMTY3MzcsMTAuMjc4MyBsIDExLjI5OTQxLDEwLjgxNDYgLTUuOTE3MzcsNS44MDQxIGMgLTE1LjkyNjE2LDE1LjYyMTQgLTE3LjE1MjY4LDE2LjY1MzYgLTE3Ljc5NjI5LDE0Ljk3NjMgeiBtIDMyLjg1OTEyLC0yNy43NzM1IGMgLTMuMzEwODksLTMuMzk5OCAtMTQuMzg1ODUsLTE0LjM5MzkgLTI0LjYxMTAzLC0yNC40MzE0IGwgLTE4LjU5MTIzLC0xOC4yNSAyNC44NjEwMywwIDI0Ljg2MTAzLDAgMCwyNC41IGMgMCwxMy40NzUgLTAuMTEyNSwyNC40NjkxIC0wLjI1LDI0LjQzMTQgLTAuMTM3NSwtMC4wMzggLTIuOTU4OTEsLTIuODUwMiAtNi4yNjk4LC02LjI1IHogbSAtODAuNDgwMiwtMjguMTgxNCAwLC0xNC41IDE4LDAgMTgsMCAwLDEzLjMgYyAwLDkuMDExMSAtMC4zODY5NywxMy42ODcgLTEuMiwxNC41IC0wLjgzODEsMC44MzgxIC02LjI2NjY3LDEuMiAtMTgsMS4yIGwgLTE2LjgsMCAwLC0xNC41IHoiCiAgICAgICAgIHN0eWxlPSJmaWxsOiMwMDAwMDAiIC8+CiAgICA8L2c+CiAgPC9nPgo8L3N2Zz4K",
    "hazard": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMjA4IgogICBoZWlnaHQ9IjE3Ny43MDk3IgogICBpZD0ic3ZnNDMyOSIKICAgdmVyc2lvbj0iMS4xIgogICBpbmtzY2FwZTp2ZXJzaW9uPSIwLjQ4LjQgcjk5MzkiCiAgIHNvZGlwb2RpOmRvY25hbWU9IkExOS5zdmciPgogIDxkZWZzCiAgICAgaWQ9ImRlZnM0MzMxIiAvPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBpZD0iYmFzZSIKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMS4wIgogICAgIGlua3NjYXBlOnBhZ2VvcGFjaXR5PSIwLjAiCiAgICAgaW5rc2NhcGU6cGFnZXNoYWRvdz0iMiIKICAgICBpbmtzY2FwZTp6b29tPSIyLjgiCiAgICAgaW5rc2NhcGU6Y3g9IjU4LjExNjM0MiIKICAgICBpbmtzY2FwZTpjeT0iNDUuNDk1NTM3IgogICAgIGlua3NjYXBlOmRvY3VtZW50LXVuaXRzPSJweCIKICAgICBpbmtzY2FwZTpjdXJyZW50LWxheWVyPSJsYXllcjEiCiAgICAgc2hvd2dyaWQ9ImZhbHNlIgogICAgIGZpdC1tYXJnaW4tdG9wPSI0IgogICAgIGZpdC1tYXJnaW4tbGVmdD0iNCIKICAgICBmaXQtbWFyZ2luLXJpZ2h0PSI0IgogICAgIGZpdC1tYXJnaW4tYm90dG9tPSI0IgogICAgIGlua3NjYXBlOndpbmRvdy13aWR0aD0iMTkyMCIKICAgICBpbmtzY2FwZTp3aW5kb3ctaGVpZ2h0PSIxMTUzIgogICAgIGlua3NjYXBlOndpbmRvdy14PSIxMjc2IgogICAgIGlua3NjYXBlOndpbmRvdy15PSItNCIKICAgICBpbmtzY2FwZTp3aW5kb3ctbWF4aW1pemVkPSIxIiAvPgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTQzMzQiPgogICAgPHJkZjpSREY+CiAgICAgIDxjYzpXb3JrCiAgICAgICAgIHJkZjphYm91dD0iIj4KICAgICAgICA8ZGM6Zm9ybWF0PmltYWdlL3N2Zyt4bWw8L2RjOmZvcm1hdD4KICAgICAgICA8ZGM6dHlwZQogICAgICAgICAgIHJkZjpyZXNvdXJjZT0iaHR0cDovL3B1cmwub3JnL2RjL2RjbWl0eXBlL1N0aWxsSW1hZ2UiIC8+CiAgICAgICAgPGRjOnRpdGxlPjwvZGM6dGl0bGU+CiAgICAgIDwvY2M6V29yaz4KICAgIDwvcmRmOlJERj4KICA8L21ldGFkYXRhPgogIDxnCiAgICAgaW5rc2NhcGU6bGFiZWw9IkxheWVyIDEiCiAgICAgaW5rc2NhcGU6Z3JvdXBtb2RlPSJsYXllciIKICAgICBpZD0ibGF5ZXIxIgogICAgIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0xMTkuNjQ3NDQsLTM3Mi41OTc3NSkiPgogICAgPGcKICAgICAgIGlkPSJnNTM1NCIKICAgICAgIHRyYW5zZm9ybT0ibWF0cml4KDEuMTc3OTU1NSwwLDAsMS4xNzc5NTU1LC0yMi4wMDM3NCwtOTcuMjE4NDA2KSI+CiAgICAgIDxyZWN0CiAgICAgICAgIHk9IjQwMy42MzM4MiIKICAgICAgICAgeD0iMTI1LjA0NTIyIgogICAgICAgICBoZWlnaHQ9IjE0MS4yNzU4NSIKICAgICAgICAgd2lkdGg9IjE2Ni45OTAxNCIKICAgICAgICAgaWQ9InJlY3Q1MzQxIgogICAgICAgICBzdHlsZT0iZmlsbDojY2YwMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjc5NTU2MDM2O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzM3NyIKICAgICAgICAgZD0ibSAyODguNDkxOTksNTQxLjc1NzUyIGMgLTEuMDkzMSwtMS40NDE3NiAtMTAuMzU0MSwtMTcuMDc5MjYgLTIwLjU4LC0zNC43NSAtMTAuMjI1OSwtMTcuNjcwNzMgLTIwLjYyNTEsLTM1LjUwMzYxIC0yMy4xMDkyLC0zOS42Mjg2MSAtMi40ODQyLC00LjEyNSAtMTEuNjEzMSwtMTkuNzgwNjYgLTIwLjI4NjQsLTM0Ljc5MDM1IC04LjY3MzMsLTE1LjAwOTY5IC0xNi4yMjY5LC0yNy4xMzc5NSAtMTYuNzg1NywtMjYuOTUxNjkgLTAuNTU4OCwwLjE4NjI2IC04LjgyNzgsMTMuODE2OTIgLTE4LjM3NTcsMzAuMjkwMzUgLTkuNTQ3OCwxNi40NzM0MyAtMTkuMzIzLDMzLjEwMTY5IC0yMS43MjI3LDM2Ljk1MTY5IC0yLjM5OTYsMy44NSAtMTIuMTM2NCwyMC41IC0yMS42MzczLDM3IC05LjUwMDgsMTYuNSAtMTguMTEwNCwzMC44MDUwMyAtMTkuMTMyMywzMS43ODg5NiAtMS44MTAxLDEuNzQyNzcgLTEuODU4MSwtMC4wMzE5IC0xLjg1ODEsLTY4Ljc1MDAxIGwgMCwtNzAuNTM4OTUgNDEsMCBjIDI2LjY2NjcsMCA0MSwwLjM0OTU5IDQxLDEgMCwwLjU1IDAuNDc2NiwxIDEuMDU5LDEgMC41ODI1LDAgMC43ODA5LC0wLjQ1IDAuNDQxLC0xIC0wLjQwODIsLTAuNjYwNTQgMTMuNDg5NiwtMSA0MC45NDEsLTEgbCA0MS41NTksMCAwLDcxIGMgMCwzOS4wNSAtMC4xMTgyLDcxIC0wLjI2MjYsNzEgLTAuMTQ0NSwwIC0xLjE1NywtMS4xNzk2MiAtMi4yNSwtMi42MjEzOSB6IG0gLTE0NS45NjkyLC02LjM0OTI0IGMgLTAuMzMsLTAuNTMzODUgMC4wNDksLTIuMjIxMzUgMC44NDIyLC0zLjc1IDEuODM2MSwtMy41Mzg1OSAzMC42MjEyLC01Mi44NjU1OSAzNy44MDI0LC02NC43NzkzNyAyLjk4MzcsLTQuOTUgOS44ODc2LC0xNi43NjI1IDE1LjM0MiwtMjYuMjUgNS40NTQ0LC05LjQ4NzUgMTAuNDkwOCwtMTcuMjUgMTEuMTkyLC0xNy4yNSAxLjU2OTIsMCAzLjM1MDcsMi43ODY0NiAxNi4zMDMyLDI1LjUgNS42NDU1LDkuOSAxMS40MTUyLDE5LjggMTIuODIxNiwyMiA3LjczNTUsMTIuMTAwODYgMzYuMTc4NCw2Mi4xODc3NSAzNi4xNzg0LDYzLjcwODkgMCwxLjcwMzA4IC0zLjE5MTQsMS43OTExIC02NC45NDEsMS43OTExIC00MC45MDU0LDAgLTY1LjE2MywtMC4zNTkyNSAtNjUuNTQwOCwtMC45NzA2MyB6IG0gMTEwLjQ4MTgsLTExLjk2NDg5IGMgMCwtMS4wNDcwMyAtMjQuNzc2MSwtNDQuMzIwODcgLTI4Ljk1MDMsLTUwLjU2NDQ4IC0zLjYyMDEsLTUuNDE0ODEgLTEzLjgxMTQsLTIyLjcxNTQ4IC0xNC42MTU3LC0yNC44MTE0MiAtMC4zNTY0LC0wLjkyODcyIC0xLjAwNSwtMS42ODg1OCAtMS40NDEzLC0xLjY4ODU4IC0wLjQzNjQsMCAtMy44Mzk4LDUuMjg3NSAtNy41NjMxLDExLjc1IC0zLjcyMzQsNi40NjI1IC03LjY5NTEsMTMuMDg3NTQgLTguODI2MSwxNC43MjIzMiAtNC4zODk1LDYuMzQ0ODcgLTI5LjMyNyw1MC40NzA4OSAtMjguODEzNCw1MC45ODQ0MyAwLjk4MjYsMC45ODI2NCA5MC4yMDk5LDAuNTk0NjUgOTAuMjA5OSwtMC4zOTIyNyB6IG0gLTc0LjUzLC05LjExMjk5IGMgLTEuMDk1NCwtMS43NzIzOSAyNy4yMzcsLTQ5Ljk1MTQ5IDI5LjM3NDYsLTQ5Ljk1MTQ5IDEuMjM3OSwwIDQuMjkwNCw0Ljc4NDk3IDE4LjE2MDYsMjguNDY3ODQgNi42MzcyLDExLjMzMjg1IDExLjc5OTcsMjEuMDM4NzYgMTEuNDcyMiwyMS41Njg2OCAtMC44NDc3LDEuMzcxNjcgLTU4LjE1ODEsMS4yODkxIC01OS4wMDc0LC0wLjA4NSB6IgogICAgICAgICBzdHlsZT0iZmlsbDojMDAwMDAwIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==",
    "parkingBrake": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjxzdmcKICAgeG1sbnM6ZGM9Imh0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvIgogICB4bWxuczpjYz0iaHR0cDovL2NyZWF0aXZlY29tbW9ucy5vcmcvbnMjIgogICB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiCiAgIHhtbG5zOnN2Zz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciCiAgIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgdmVyc2lvbj0iMS4wIgogICB3aWR0aD0iMjA4IgogICBoZWlnaHQ9IjE2My4xMTI1MiIKICAgdmlld0JveD0iMCAwIDE2Ni40IDEzMC40OTAwMSIKICAgcHJlc2VydmVBc3BlY3RSYXRpbz0ieE1pZFlNaWQgbWVldCIKICAgaWQ9InN2ZzIiCiAgIGlua3NjYXBlOnZlcnNpb249IjAuNDguNCByOTkzOSIKICAgc29kaXBvZGk6ZG9jbmFtZT0iQjAyLnN2ZyI+CiAgPGRlZnMKICAgICBpZD0iZGVmczE4IiAvPgogIDxzb2RpcG9kaTpuYW1lZHZpZXcKICAgICBwYWdlY29sb3I9IiNmZmZmZmYiCiAgICAgYm9yZGVyY29sb3I9IiM2NjY2NjYiCiAgICAgYm9yZGVyb3BhY2l0eT0iMSIKICAgICBvYmplY3R0b2xlcmFuY2U9IjEwIgogICAgIGdyaWR0b2xlcmFuY2U9IjEwIgogICAgIGd1aWRldG9sZXJhbmNlPSIxMCIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMCIKICAgICBpbmtzY2FwZTpwYWdlc2hhZG93PSIyIgogICAgIGlua3NjYXBlOndpbmRvdy13aWR0aD0iMTkyMCIKICAgICBpbmtzY2FwZTp3aW5kb3ctaGVpZ2h0PSIxMTUzIgogICAgIGlkPSJuYW1lZHZpZXcxNiIKICAgICBzaG93Z3JpZD0iZmFsc2UiCiAgICAgZml0LW1hcmdpbi10b3A9IjQiCiAgICAgZml0LW1hcmdpbi1sZWZ0PSI0IgogICAgIGZpdC1tYXJnaW4tcmlnaHQ9IjQiCiAgICAgZml0LW1hcmdpbi1ib3R0b209IjQiCiAgICAgaW5rc2NhcGU6em9vbT0iMy4zMzU3OTQ1IgogICAgIGlua3NjYXBlOmN4PSIxMjMuNDY1NjQiCiAgICAgaW5rc2NhcGU6Y3k9IjEwNy4xNjE4MiIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iMTI3NiIKICAgICBpbmtzY2FwZTp3aW5kb3cteT0iLTQiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0iMSIKICAgICBpbmtzY2FwZTpjdXJyZW50LWxheWVyPSJzdmcyIiAvPgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTQiPgpDcmVhdGVkIGJ5IHBvdHJhY2UgMS4xMSwgd3JpdHRlbiBieSBQZXRlciBTZWxpbmdlciAyMDAxLTIwMTMKPHJkZjpSREY+CiAgPGNjOldvcmsKICAgICByZGY6YWJvdXQ9IiI+CiAgICA8ZGM6Zm9ybWF0PmltYWdlL3N2Zyt4bWw8L2RjOmZvcm1hdD4KICAgIDxkYzp0eXBlCiAgICAgICByZGY6cmVzb3VyY2U9Imh0dHA6Ly9wdXJsLm9yZy9kYy9kY21pdHlwZS9TdGlsbEltYWdlIiAvPgogICAgPGRjOnRpdGxlPjwvZGM6dGl0bGU+CiAgPC9jYzpXb3JrPgo8L3JkZjpSREY+CjwvbWV0YWRhdGE+CiAgPHJlY3QKICAgICBzdHlsZT0iZmlsbDojY2YwMDAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoxLjg1MDU4NzAxO3N0cm9rZS1saW5lam9pbjptaXRlcjtzdHJva2UtbWl0ZXJsaW1pdDo0O3N0cm9rZS1vcGFjaXR5OjE7c3Ryb2tlLWRhc2hhcnJheTpub25lIgogICAgIGlkPSJyZWN0Mjk5NSIKICAgICB3aWR0aD0iMTU4LjE0OTQxIgogICAgIGhlaWdodD0iMTIyLjIzOTQzIgogICAgIHg9IjQuMTI1MjkzNyIKICAgICB5PSI0LjEyNTI5MTMiIC8+CiAgPGcKICAgICB0cmFuc2Zvcm09Im1hdHJpeCgwLjA4MTM3Nzk5LDAsMCwtMC4wODEzNzc5OSw0LjE1ODk1ODQsMTI2LjMzMTA0KSIKICAgICBpZD0iZzYiCiAgICAgc3R5bGU9ImZpbGw6IzAwMDAwMDtzdHJva2U6bm9uZSI+CiAgICA8cGF0aAogICAgICAgZD0iTSAxLDExNzMgQyAyLDk5MiA1LDg1OSA3LDg3NSBjIDI0LDE5MyAxMTksMzk3IDI1Miw1MzggbCAzNSwzNyAzOCwtMzcgYyAyMSwtMjAgMzgsLTQwIDM4LC00NCAwLC01IC0xNiwtMjUgLTM2LC00NiBDIDExMiwxMDg2IDUzLDcwNSAxOTEsNDAyIDIyNywzMjEgMjc0LDI1MCAzMzUsMTgyIEwgMzgxLDEzMSAzNDksOTAgQyAzMzEsNjggMzEzLDUwIDMwOSw1MCAyOTIsNTAgMTgyLDE4NSAxMzMsMjY2IDc4LDM1OCAyNiw1MDQgMTEsNjA1IDUsNjQ3IDIsNTYzIDEsMzMzIEwgMCwwIDQ0MywxIGMgMjU3LDEgNDIyLDUgMzk1LDkgLTIyNCwzOCAtNDI3LDE4OCAtNTM2LDM5NSAtNjMsMTE5IC03NywxODQgLTc3LDM1MCAxLDEzNSAzLDE1OCAyNywyMjggMzcsMTExIDEwMCwyMTEgMTg3LDI5OCAxMTEsMTExIDIzNSwxNzggMzg2LDIwOSAyMyw0IC0xNDAsOCAtMzkyLDkgbCAtNDMzLDEgMSwtMzI3IHoiCiAgICAgICBpZD0icGF0aDgiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgPHBhdGgKICAgICAgIGQ9Im0gMTEwMCwxNDkzIGMgNDQsLTcgMTUzLC00NSAyMDUsLTcxIDE3OSwtODggMzE3LC0yNTAgMzgyLC00NDcgMjMsLTcxIDI2LC05NiAyNywtMjIwIDAsLTExOSAtMywtMTUxIC0yMywtMjE1IEMgMTYwNywyNjcgMTM3Myw1NiAxMTAyLDEwIDEwNzUsNiAxMjQwLDIgMTQ5OCwxIGwgNDQyLC0xIC0xLDM1MyBjIC0xLDIyMyAtNCwzMjggLTksMjg2IEMgMTkwNyw0NDIgMTgxNiwyNDUgMTY4MSw5OSBsIC00OSwtNTQgLTI3LDI1IGMgLTUyLDQ4IC01MSw1NCAxNCwxMzIgMjczLDMyNCAyNjcsODAzIC0xMywxMTE1IGwgLTQ1LDUwIDQzLDQyIDQzLDQyIDQzLC00OCBjIDEyOSwtMTQ1IDIxNywtMzQyIDI0MCwtNTMyIDUsLTQyIDgsNjAgOSwyODIgbCAxLDM0NyAtNDMyLC0xIGMgLTIzOCwtMSAtNDIyLC00IC00MDgsLTYgeiIKICAgICAgIGlkPSJwYXRoMTAiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogICAgPHBhdGgKICAgICAgIGQ9Ik0gODEwLDEzNzQgQyA1ODAsMTMxNSAzOTIsMTEyMCAzNDAsODkwIDMyNSw4MjIgMzI4LDY2MiAzNDUsNTk1IDM5NCw0MDQgNTQ1LDIyOSA3MjYsMTU2IGMgMTg1LC03NSA0MTUsLTU2IDU4MSw0OSAxMjUsNzkgMjI3LDIwOSAyNzQsMzUwIDIxLDYwIDI0LDg4IDIzLDIwMCAtMSwxMTQgLTQsMTM5IC0yNywyMDQgLTc0LDIwNyAtMjQyLDM2MSAtNDUyLDQxNiAtNzQsMTkgLTI0MSwxOSAtMzE1LC0xIHogbSAzMDUsLTE5NiBjIDgxLC0xNiAxNDMsLTYwIDE3OCwtMTI4IDI3LC01MSAyOSwtNjIgMjUsLTE0MCAtNSwtMTE0IC00NCwtMTc3IC0xNDMsLTIyOCAtNDUsLTI0IC02MywtMjYgLTE5MiwtMzAgbCAtMTQzLC00IDAsLTE2NCAwLC0xNjQgLTU1LDAgLTU1LDAgMCw0MzUgMCw0MzUgMTYzLDAgYyA5MCwwIDE5MCwtNSAyMjIsLTEyIHoiCiAgICAgICBpZD0icGF0aDEyIgogICAgICAgaW5rc2NhcGU6Y29ubmVjdG9yLWN1cnZhdHVyZT0iMCIgLz4KICAgIDxwYXRoCiAgICAgICBkPSJtIDg0MCw5MjAgMCwtMTYwIDEyMCwwIGMgMTM5LDAgMTY0LDkgMjEwLDcyIDU3LDc4IDMzLDE4OSAtNTAsMjMwIC0yOCwxNCAtNjEsMTggLTE1NywxOCBsIC0xMjMsMCAwLC0xNjAgeiIKICAgICAgIGlkPSJwYXRoMTQiCiAgICAgICBpbmtzY2FwZTpjb25uZWN0b3ItY3VydmF0dXJlPSIwIiAvPgogIDwvZz4KPC9zdmc+Cg==",
    "bulbFailure": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhLS0gQ3JlYXRlZCB3aXRoIElua3NjYXBlIChodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy8pIC0tPgoKPHN2ZwogICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgIHhtbG5zOmNjPSJodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9ucyMiCiAgIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyIKICAgeG1sbnM6c3ZnPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIgogICB4bWxuczpzb2RpcG9kaT0iaHR0cDovL3NvZGlwb2RpLnNvdXJjZWZvcmdlLm5ldC9EVEQvc29kaXBvZGktMC5kdGQiCiAgIHhtbG5zOmlua3NjYXBlPSJodHRwOi8vd3d3Lmlua3NjYXBlLm9yZy9uYW1lc3BhY2VzL2lua3NjYXBlIgogICB3aWR0aD0iMjA4IgogICBoZWlnaHQ9IjE5Mi43OTM2NCIKICAgaWQ9InN2ZzQzMjkiCiAgIHZlcnNpb249IjEuMSIKICAgaW5rc2NhcGU6dmVyc2lvbj0iMC40OC40IHI5OTM5IgogICBzb2RpcG9kaTpkb2NuYW1lPSJBMTQuc3ZnIj4KICA8ZGVmcwogICAgIGlkPSJkZWZzNDMzMSIgLz4KICA8c29kaXBvZGk6bmFtZWR2aWV3CiAgICAgaWQ9ImJhc2UiCiAgICAgcGFnZWNvbG9yPSIjZmZmZmZmIgogICAgIGJvcmRlcmNvbG9yPSIjNjY2NjY2IgogICAgIGJvcmRlcm9wYWNpdHk9IjEuMCIKICAgICBpbmtzY2FwZTpwYWdlb3BhY2l0eT0iMC4wIgogICAgIGlua3NjYXBlOnBhZ2VzaGFkb3c9IjIiCiAgICAgaW5rc2NhcGU6em9vbT0iMi44IgogICAgIGlua3NjYXBlOmN4PSI3NC41MjU3NzUiCiAgICAgaW5rc2NhcGU6Y3k9Ijg2LjU5ODc3MiIKICAgICBpbmtzY2FwZTpkb2N1bWVudC11bml0cz0icHgiCiAgICAgaW5rc2NhcGU6Y3VycmVudC1sYXllcj0ibGF5ZXIxIgogICAgIHNob3dncmlkPSJmYWxzZSIKICAgICBmaXQtbWFyZ2luLXRvcD0iNCIKICAgICBmaXQtbWFyZ2luLWxlZnQ9IjQiCiAgICAgZml0LW1hcmdpbi1yaWdodD0iNCIKICAgICBmaXQtbWFyZ2luLWJvdHRvbT0iNCIKICAgICBpbmtzY2FwZTp3aW5kb3ctd2lkdGg9IjE5MjAiCiAgICAgaW5rc2NhcGU6d2luZG93LWhlaWdodD0iMTE1MyIKICAgICBpbmtzY2FwZTp3aW5kb3cteD0iMTI3NiIKICAgICBpbmtzY2FwZTp3aW5kb3cteT0iLTQiCiAgICAgaW5rc2NhcGU6d2luZG93LW1heGltaXplZD0iMSIgLz4KICA8bWV0YWRhdGEKICAgICBpZD0ibWV0YWRhdGE0MzM0Ij4KICAgIDxyZGY6UkRGPgogICAgICA8Y2M6V29yawogICAgICAgICByZGY6YWJvdXQ9IiI+CiAgICAgICAgPGRjOmZvcm1hdD5pbWFnZS9zdmcreG1sPC9kYzpmb3JtYXQ+CiAgICAgICAgPGRjOnR5cGUKICAgICAgICAgICByZGY6cmVzb3VyY2U9Imh0dHA6Ly9wdXJsLm9yZy9kYy9kY21pdHlwZS9TdGlsbEltYWdlIiAvPgogICAgICAgIDxkYzp0aXRsZT48L2RjOnRpdGxlPgogICAgICA8L2NjOldvcms+CiAgICA8L3JkZjpSREY+CiAgPC9tZXRhZGF0YT4KICA8ZwogICAgIGlua3NjYXBlOmxhYmVsPSJMYXllciAxIgogICAgIGlua3NjYXBlOmdyb3VwbW9kZT0ibGF5ZXIiCiAgICAgaWQ9ImxheWVyMSIKICAgICB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMTAzLjIzODAxLC0zOTguNjE3MDUpIj4KICAgIDxnCiAgICAgICBpZD0iZzUyMjMiCiAgICAgICB0cmFuc2Zvcm09Im1hdHJpeCgxLjAxMzc1ODIsMCwwLDEuMDEzNzU4MiwtMS40NzUzOTc4LC04LjA4MTY5MDkpIj4KICAgICAgPHJlY3QKICAgICAgICAgeT0iNDA2LjQ5MiIKICAgICAgICAgeD0iMTA4LjYwNTA2IgogICAgICAgICBoZWlnaHQ9IjE3OS41NTE2MSIKICAgICAgICAgd2lkdGg9IjE5NC41NTE2MSIKICAgICAgICAgaWQ9InJlY3Q1MjIxIgogICAgICAgICBzdHlsZT0iZmlsbDojZTBiMzAwO2ZpbGwtb3BhY2l0eToxO2ZpbGwtcnVsZTpldmVub2RkO3N0cm9rZTojMDAwMDAwO3N0cm9rZS13aWR0aDoyLjczNDEwNjA2O3N0cm9rZS1taXRlcmxpbWl0OjQ7c3Ryb2tlLW9wYWNpdHk6MTtzdHJva2UtZGFzaGFycmF5Om5vbmUiIC8+CiAgICAgIDxwYXRoCiAgICAgICAgIGlua3NjYXBlOmNvbm5lY3Rvci1jdXJ2YXR1cmU9IjAiCiAgICAgICAgIGlkPSJwYXRoMzI5OSIKICAgICAgICAgZD0ibSAxMDkuMzgwODgsNTQwLjE1MTA3IDAsLTQ1LjQ3NCAxNS4yNSwtMC4yNzYwNCAxNS4yNSwtMC4yNzYwNSAwLC01IDAsLTUgLTE1LjI1LC0wLjI3NjA1IC0xNS4yNSwtMC4yNzYwNCAwLC0zNy45NzM5NiAwLC0zNy45NzM5NSAzNSwwIDM1LDAgMCwxNy4wMDY2MSAwLDE3LjAwNjYyIC0yLjc1LDIuMjI3OTUgYyAtMS41MTI1LDEuMjI1MzggLTUuNDc1MzUsNC45MzU0MyAtOC44MDYzNSw4LjI0NDU3IC0xMC45MzAxNiwxMC44NTg0MyAtMTYuNDk0LDI2LjMwMzAzIC0xNS4wNTQ2NCw0MS43ODk5NyAyLjAxNjY2LDIxLjY5ODUzIDE1LjU2NjU1LDM4Ljk2MTExIDM2LjMzNDg1LDQ2LjI5MDY3IDUuNDk2NTYsMS45Mzk4IDguNzU4OTIsMi4zOTE0IDE3LjI3NjE0LDIuMzkxNCA4LjU5MTM2LDAgMTEuNzY0MjgsLTAuNDQ2MSAxNy40NTUxNywtMi40NTQgMjYuNTkzMTQsLTkuMzgyODMgNDEuMjk5MzcsLTM3LjE5NzAzIDM0LjM2OTUzLC02NS4wMDM3OSAtMS4zMTM3NCwtNS4yNzE1NiAtNi4yNzQ5OSwtMTUuMDE4MTMgLTEwLjEwODE4LC0xOS44NTc5MyAtMS42ODcwOSwtMi4xMzAxMiAtNS4zNTA5OCwtNS42MjQ3IC04LjE0MTk4LC03Ljc2NTczIC0yLjc5MSwtMi4xNDEwMyAtNS42MzcwNCwtNC4zNTY4MyAtNi4zMjQ1NCwtNC45MjM5OSAtMC45MTAzMywtMC43NTA5OSAtMS4yNSwtNS42Mzk5NiAtMS4yNSwtMTcuOTkxNzggbCAwLC0xNi45NjA1NyAzNSwwIDM1LDAgMCwzNy45NzMyNyAwLDM3Ljk3MzI2IC0xNC43NSwwLjI3Njc0IC0xNC43NSwwLjI3NjczIDAsNSAwLDUgMTQuNzUsMC4yNzY3MyAxNC43NSwwLjI3Njc0IDAsNDUuNDczMjIgMCw0NS40NzMzIC00NS40NzMyNywwIC00NS40NzMyNiwwIC0wLjI3Njc0LC0xNC43NSAtMC4yNzY3MywtMTQuNzUgLTUsMCAtNSwwIC0wLjI3NjczLDE0Ljc1IC0wLjI3Njc0LDE0Ljc1IC00NS40NzMyNiwwIC00NS40NzMyNywwIDAsLTQ1LjQ3MzkgeiBtIDQzLjk4MTc3LDkuOTkyMiAxMC40NDYwMywtMTAuNDgxNyAtMy40MTAwNywtMy41MTgzIGMgLTEuODc1NTMsLTEuOTM1MSAtMy44OTIzMywtMy41MTgyOSAtNC40ODE3NiwtMy41MTgyOSAtMC41ODk0NCwwIC01Ljc3MjQyLDQuNzE2NzkgLTExLjUxNzc0LDEwLjQ4MTY5IGwgLTEwLjQ0NjAzLDEwLjQ4MTcgMy40MTAwNywzLjUxODMgYyAxLjg3NTUzLDEuOTM1MSAzLjg5MjMzLDMuNTE4MyA0LjQ4MTc2LDMuNTE4MyAwLjU4OTQ0LDAgNS43NzI0MiwtNC43MTY4IDExLjUxNzc0LC0xMC40ODE3IHogbSAxMjEuMjEzNTEsNy43OTQ2IGMgMS41NDI2LC0xLjQ3NzkgMi44MDQ3MiwtMy4yNTI5IDIuODA0NzIsLTMuOTQ0NCAwLC0xLjI5ODIgLTE5LjYyNTE4LC0yMS4zNjg0OSAtMjAuODk0NjQsLTIxLjM2ODQ5IC0wLjM5MjE3LDAgLTIuMjQ3NTYsMS41ODMxOSAtNC4xMjMwOSwzLjUxODI5IGwgLTMuNDEwMDcsMy41MTgzIDEwLjQ0NjAzLDEwLjQ4MTcgYyA1Ljc0NTMyLDUuNzY0OSAxMC44Nzk0NSwxMC40ODE3IDExLjQwOTE4LDEwLjQ4MTcgMC41Mjk3NCwwIDIuMjI1MjgsLTEuMjA5MiAzLjc2Nzg3LC0yLjY4NzEgeiBtIC0xMTUsLTExNC45OTk5OCBjIDEuNTQyNiwtMS40Nzc5IDIuODA0NzIsLTMuMjU2MzIgMi44MDQ3MiwtMy45NTIwNCAwLC0xLjYwMzk0IC0xOS4wNTQ5OCwtMjAuMzYwODcgLTIwLjY4NDQsLTIwLjM2MDg3IC0xLjcwNTExLDAgLTYuMzE1Niw0LjQ1MDc1IC02LjMxNTYsNi4wOTY3OCAwLDEuNTM2NzkgMTguOTI0NzgsMjAuOTAzMjIgMjAuNDI2NTIsMjAuOTAzMjIgMC41MzAyMiwwIDIuMjI2MTcsLTEuMjA5MTkgMy43Njg3NiwtMi42ODcwOSB6IG0gMTA4LjAzNjgzLC03LjA0NDE1IGMgNS4zNzIzNCwtNS4zNTIxOCA5Ljc2Nzg5LC0xMC4yMTM5IDkuNzY3ODksLTEwLjgwMzgzIDAsLTAuNTg5OTMgLTEuNTg1OTcsLTIuNjA5NzggLTMuNTI0MzgsLTQuNDg4NTcgbCAtMy41MjQzOSwtMy40MTU5NiAtMTAuNjk1NDIsMTAuNjk1NDEgLTEwLjY5NTQxLDEwLjY5NTQyIDMuNDE1OTcsMy41MjQzOCBjIDEuODc4NzgsMS45Mzg0MiAzLjg4MjE0LDMuNTI0MzkgNC40NTE5MSwzLjUyNDM5IDAuNTY5NzYsMCA1LjQzMTQ5LC00LjM3OTA2IDEwLjgwMzgzLC05LjczMTI0IHogbSAtNzIuNDg2MTksOTUuNzA3NDkgYyAtMTAuNzcwMDIsLTIuNzE1OTUgLTIyLjg3NzQzLC0xMi42NTkxOCAtMjcuOTc3MTIsLTIyLjk3NjI1IC0xLjQ5NTI1LC0zLjAyNSAtMy4yNzA4MSwtOC43NTgzNyAtMy45NDU2OSwtMTIuNzQwODEgLTAuOTczNjksLTUuNzQ1NzEgLTAuOTcwMDEsLTguNTMzMjQgMC4wMTc4LC0xMy41IDEuNzM0MzIsLTguNzIwMDggNi42NDYzMywtMTguMzQxNyAxMi4xOTc5NywtMjMuODkzMzQgNy43MDE2OSwtNy43MDE2OSAxOS44NjgwNiwtMTIuODI4OTQgMzAuNTAwOTksLTEyLjg1Mzk4IDYuNTI0OSwtMC4wMTU0IDE1LjUzMzQ3LDIuMzU4OTcgMjEuNzE0NzEsNS43MjMyMiA1LjY4NjQ3LDMuMDk0OTcgMTQuODUwMzgsMTIuNTkwMjIgMTcuODc3NTQsMTguNTIzOTUgMS4xNTEyNCwyLjI1NjYgMi42OTk2Myw3LjU3NjkxIDMuNDQwODgsMTEuODIyOTEgMC45OTU5Myw1LjcwNDgxIDEuMDg5ODQsOS4zNzczIDAuMzU5NzYsMTQuMDY5MDIgLTIuMTg5MjMsMTQuMDY4NzMgLTExLjg4NjM0LDI3LjEyNDYzIC0yNC41NDY5LDMzLjA0OTIyIC01Ljc1Mjg4LDIuNjkyMSAtNy45NzMxNywzLjE1ODcxIC0xNi4yNzM4MywzLjQyMDA5IC01LjI4NjYzLDAuMTY2NDcgLTExLjMwMTM5LC0wLjEyMzM0IC0xMy4zNjYxMywtMC42NDQwMyB6IG0gMTYuNTA0MDgsLTEwLjEyOTY4IGMgMC45NjI1LC0xLjEzNzQ3IDEuNzUsLTMuMTYzNzQgMS43NSwtNC41MDI4MSAwLC0zLjE4MTgxIC00LjIyNDczLC03LjM0Mzc2IC03LjQ1NDU1LC03LjM0Mzc2IC0zLjYyMzQ5LDAgLTYuNTQ1NDUsMy4zMTU2NyAtNi41NDU0NSw3LjQyNzQyIDAsMi41MzQ2NSAwLjcwNTA0LDMuOTgyMDEgMi43MDY3Miw1LjU1NjUyIDMuMTY2MDksMi40OTA0NiA2Ljg0NDQ4LDIuMDUyMDcgOS41NDMyOCwtMS4xMzczNyB6IG0gLTAuNzA0NTUsLTE4LjMwMTEyIDIuNDU0NTUsLTIuNDU0NTQgMCwtMjEuOTM0NjcgYyAwLC0xOS44MjY4OCAtMC4xNzcyMSwtMjIuMTUzNTIgLTEuODQ0MTcsLTI0LjIxMjEyIC0yLjUwNzI3LC0zLjA5NjM2IC03LjgwNDM5LC0zLjA5NjM2IC0xMC4zMTE2NiwwIC0xLjY2OTEsMi4wNjEyNSAtMS44NDQxNyw0LjM5NiAtMS44NDQxNywyNC41OTQwOCBsIDAsMjIuMzE2NjQgMi42MzQ4NiwyLjA3MjU4IGMgMS40NDkxNywxLjEzOTkyIDMuNDk0NjMsMi4wNzI1OCA0LjU0NTQ1LDIuMDcyNTggMS4wNTA4MywwIDMuMDE1MTQsLTEuMTA0NTUgNC4zNjUxNCwtMi40NTQ1NSB6IG0gNC45NTQ1NSwtNjYuNzM4IGMgLTIuMjI1MTEsLTAuNTQ1NjEgLTguNzg2NzksLTAuNzExNjEgLTE0Ljc4Nzc5LC0wLjM3NDA5IGwgLTEwLjc4Nzc5LDAuNjA2NzMgMC4yODc3OSwtOS4yNzAwNCAwLjI4Nzc5LC05LjI3MDA1IDE1LjUsMCAxNS41LDAgMCw5LjQxNjY3IGMgMCw1LjQ1OTQ2IC0wLjQyMDIzLDkuNTEyMjYgLTEsOS42NDQxNCAtMC41NSwwLjEyNTExIC0yLjgsLTAuMjEzOSAtNSwtMC43NTMzNiB6IgogICAgICAgICBzdHlsZT0iZmlsbDojMDAwMDAwIiAvPgogICAgPC9nPgogIDwvZz4KPC9zdmc+Cg==",
    "highBeam": "data:image/png;base64,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",
    "dippedBeam": "data:image/png;base64,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",
    "rearFog": "data:image/png;base64,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",
    "positionLights": "data:image/png;base64,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"
});

  const FORCED_FROM_URL = parseForcedTokens();
  const forcedFromKeyboard = new Set();
  let lastPayload = null;
  let renderRaf = 0;

  const SLOT_DEFS = [
    { key: "left", label: "Left indicator", kind: "left-turn", src: ICONS.leftTurn },
    { key: "right", label: "Right indicator", kind: "right-turn", src: ICONS.rightTurn },
    { key: "park", label: "Parking brake", kind: "parking-brake", src: ICONS.parkingBrake },
    { key: "hazard", label: "Hazard warning", kind: "hazard", src: ICONS.hazard },
    { key: "bulb", label: "Exterior bulb failure", kind: "bulb-failure", src: ICONS.bulbFailure },
    { key: "sidelights", label: "Side/position lights", kind: "position-lights wide", src: ICONS.positionLights },
    { key: "dipped", label: "Dipped beam", kind: "dipped-beam wide", src: ICONS.dippedBeam },
    { key: "highbeam", label: "High beam", kind: "high-beam wide", src: ICONS.highBeam },
    { key: "rearfog", label: "Rear fog light", kind: "rear-fog square", src: ICONS.rearFog },
  ];

  const KEY_BINDINGS = new Map([
    ["1", "left"],
    ["2", "right"],
    ["3", "hazard"],
    ["4", "park"],
    ["5", "bulb"],
    ["6", "sidelights"],
    ["7", "dipped"],
    ["8", "highbeam"],
    ["9", "rearfog"],
    ["0", "all"],
  ]);

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function normaliseToken(token) {
    const clean = String(token || "").trim().toLowerCase().replace(/_/g, "-");
    const compact = clean.replace(/[-\s]/g, "");
    const aliases = new Map([
      ["parking", "park"], ["handbrake", "park"], ["parkingbrake", "park"], ["parking-brake", "park"],
      ["l", "left"], ["leftindicator", "left"], ["left-indicator", "left"],
      ["r", "right"], ["rightindicator", "right"], ["right-indicator", "right"],
      ["hazards", "hazard"],
      ["lamp", "sidelights"], ["light", "sidelights"], ["lights", "sidelights"], ["side", "sidelights"], ["sidelight", "sidelights"], ["side-light", "sidelights"], ["position", "sidelights"], ["positionlights", "sidelights"], ["position-lights", "sidelights"], ["parkinglights", "sidelights"], ["parking-lights", "sidelights"],
      ["dip", "dipped"], ["dippedbeam", "dipped"], ["dipped-beam", "dipped"], ["lowbeam", "dipped"], ["low-beam", "dipped"], ["headlamp", "dipped"], ["headlight", "dipped"], ["headlights", "dipped"],
      ["mainbeam", "highbeam"], ["main-beam", "highbeam"], ["high-beam", "highbeam"], ["fullbeam", "highbeam"], ["full-beam", "highbeam"],
      ["rear", "rearfog"], ["rear-fog", "rearfog"], ["rearfoglight", "rearfog"], ["rear-fog-light", "rearfog"], ["fogrear", "rearfog"], ["fog-rear", "rearfog"],
      ["bulbout", "bulb"], ["bulb-out", "bulb"], ["bulbfault", "bulb"], ["bulb-fault", "bulb"],
      ["lowvoltage", "voltage"], ["low-voltage", "voltage"], ["battery", "voltage"],
      ["hot", "coolant"], ["overheat", "coolant"], ["dooropen", "door"], ["door-open", "door"],
      ["all", "all"],
    ]);
    return aliases.get(clean) || aliases.get(compact) || clean;
  }

  function parseForcedTokens() {
    const params = new URLSearchParams(window.location.search || "");
    const raw = [
      params.get("force"),
      params.get("telltale"),
      params.get("telltales"),
      params.get("warn"),
      params.get("warnings"),
    ].filter(Boolean).join(",");
    const tokens = new Set();
    raw.split(/[\s,;+|]+/).map(normaliseToken).filter(Boolean).forEach((token) => tokens.add(token));
    return tokens;
  }

  function forced(token) {
    return FORCED_FROM_URL.has("all") || forcedFromKeyboard.has("all") || FORCED_FROM_URL.has(token) || forcedFromKeyboard.has(token);
  }

  function anyForced() {
    return FORCED_FROM_URL.size > 0 || forcedFromKeyboard.size > 0;
  }

  function clonePayload(payload) {
    try { return JSON.parse(JSON.stringify(payload || {})); }
    catch (_error) { return Object.assign({}, payload || {}); }
  }

  function applyTestOverrides(payload) {
    if (!anyForced()) return payload;
    const copy = clonePayload(payload);
    copy.state = copy.state || {};
    const state = copy.state;
    state.vehicle = state.vehicle || {};
    state.lighting = state.lighting || {};
    state.electrical = state.electrical || {};
    state.engine = state.engine || {};
    state.doors = state.doors || {};
    const lighting = state.lighting;

    if (forced("left")) lighting.left_indicator = true;
    if (forced("right")) lighting.right_indicator = true;
    if (forced("hazard")) { lighting.hazards = true; lighting.left_indicator = true; lighting.right_indicator = true; }
    if (forced("park")) state.vehicle.handbrake = true;
    if (forced("bulb")) lighting.bulb_out = true;
    if (forced("sidelights")) { lighting.side_lights = true; lighting.position_lights = true; lighting.lights_on = true; lighting.mode = "side lights"; }
    if (forced("dipped")) { lighting.dipped_beam = true; lighting.low_beam = true; lighting.lights_on = true; lighting.mode = "dipped beam"; }
    if (forced("highbeam")) { lighting.high_beam = true; lighting.main_beam = true; lighting.lights_on = true; lighting.mode = "high beam"; }
    if (forced("rearfog")) { lighting.rear_fog = true; lighting.rear_fog_light = true; }
    if (forced("door")) { state.doors.any_open = true; state.doors.driver_open = true; }
    if (forced("voltage")) { state.electrical.voltage_v = 11.4; state.electrical.low_voltage = true; }
    if (forced("coolant")) { state.engine.coolant_temp_c = 118; state.engine.coolant_warning = true; }
    copy.test_mode = true;
    copy.test_telltales = Array.from(new Set([...FORCED_FROM_URL, ...forcedFromKeyboard]));
    return copy;
  }

  function truthy(value) {
    if (value === true) return true;
    if (value === false || value == null) return false;
    const text = String(value).trim().toLowerCase();
    return ["1", "true", "yes", "on", "active", "enabled"].includes(text);
  }

  function hasOwn(object, key) {
    return !!object && Object.prototype.hasOwnProperty.call(object, key);
  }

  function textIncludes(text, patterns) {
    const value = String(text || "").toLowerCase();
    return patterns.some((pattern) => pattern.test(value));
  }

  function lightingMode(lighting) {
    return String((lighting && lighting.mode) || "").trim().toLowerCase();
  }

  function sideLightsOn(lighting) {
    const mode = lightingMode(lighting);
    return truthy(lighting.side_lights) || truthy(lighting.sidelights) || truthy(lighting.position_lights) || truthy(lighting.parking_lights) ||
      ["sides", "dip", "rear_fog", "main_beam_sides", "main_beam_dip", "main_beam_rear_fog", "sides_with_reverse", "reverse_with_dip", "rear_fog_with_reverse"].includes(mode) ||
      textIncludes(mode, [/\bsides?\b/, /sidelight/, /position/, /parking light/, /park light/]);
  }

  function dippedBeamOn(lighting) {
    const mode = lightingMode(lighting);
    return truthy(lighting.dipped_beam) || truthy(lighting.low_beam) || truthy(lighting.dip_beam) || truthy(lighting.headlights) || truthy(lighting.head_lights) ||
      ["dip", "rear_fog", "main_beam_dip", "main_beam_rear_fog", "reverse_with_dip", "rear_fog_with_reverse"].includes(mode) ||
      textIncludes(mode, [/dipped/, /\bdip\b/, /low beam/, /headlight/, /headlamp/]);
  }

  function highBeamOn(lighting) {
    const mode = lightingMode(lighting);
    return truthy(lighting.high_beam) || truthy(lighting.main_beam) || truthy(lighting.full_beam) ||
      ["main_beam_lights_off", "main_beam_sides", "main_beam_dip", "main_beam_rear_fog"].includes(mode) ||
      textIncludes(mode, [/high beam/, /main beam/, /full beam/]);
  }

  function rearFogOn(lighting) {
    const mode = lightingMode(lighting);
    return truthy(lighting.rear_fog) || truthy(lighting.rear_fog_light) || truthy(lighting.fog_rear) || truthy(lighting.fog_lights_rear) ||
      ["rear_fog", "main_beam_rear_fog", "rear_fog_with_reverse"].includes(mode) ||
      textIncludes(mode, [/rear fog/, /fog rear/]);
  }

  function knownAny(lighting, keys, forcedKey) {
    return forced(forcedKey) || keys.some((key) => hasOwn(lighting, key)) || !!String(lighting.mode || "").trim();
  }

  function findFooter() {
    return document.querySelector(".status-strip") ||
      document.querySelector("footer.status-strip") ||
      document.querySelector(".screen > footer") ||
      document.querySelector("footer") ||
      document.querySelector(".footer") ||
      document.querySelector(".bottom-bar");
  }

  function ensureStrip() {
    const footer = findFooter();
    if (!footer) return null;
    footer.classList.add("openmmi-footer-black", "openmmi-footer-with-telltales", "openmmi-footer-centred-telltales", "openmmi-stable-footer-telltales");
    let strip = footer.querySelector("#openMmiFooterTelltales");
    if (!strip) {
      strip = document.createElement("div");
      strip.id = "openMmiFooterTelltales";
      strip.className = "openmmi-footer-telltales openmmi-footer-telltales-centred openmmi-stable-footer-telltales-strip";
      footer.insertBefore(strip, footer.firstChild);
    }
    if (strip.dataset.openMmiSlotVersion !== "proper-light-v1") {
      strip.innerHTML = SLOT_DEFS.map(slotMarkup).join("");
      strip.dataset.openMmiSlotVersion = "proper-light-v1";
    }
    return strip;
  }

  function slotMarkup(slot) {
    return `<span class="openmmi-footer-telltale openmmi-footer-telltale-${esc(slot.kind)} openmmi-footer-slot-${esc(slot.key)} is-inactive" data-openmmi-telltale-slot="${esc(slot.key)}" role="img" aria-label="${esc(slot.label + ': off')}" title="${esc(slot.label + ': off')}">` +
      `<img src="${slot.src}" alt="" aria-hidden="true" loading="eager" decoding="async" draggable="false">` +
      `<span class="openmmi-footer-telltale-sr">${esc(slot.label + ': off')}</span>` +
      `</span>`;
  }

  function setSlot(strip, key, active, known, label, options) {
    const slot = strip.querySelector(`[data-openmmi-telltale-slot="${key}"]`);
    if (!slot) return;
    const on = active === true;
    const usable = known !== false;
    const text = `${label}: ${on ? "on" : "off"}`;
    slot.classList.toggle("is-active", on);
    slot.classList.toggle("is-inactive", !on && usable);
    slot.classList.toggle("is-unknown", !usable);
    slot.classList.toggle("is-forced-blink", !!(options && options.forcedBlink && on));
    slot.setAttribute("aria-label", text);
    slot.setAttribute("title", text);
    const sr = slot.querySelector(".openmmi-footer-telltale-sr");
    if (sr) sr.textContent = text;
  }

  function hideMovedPageTelltales() {
    const selectors = [
      '[data-field="indicators"]', '[data-bool="handbrake"]', '[data-bool="hazards"]', '[data-bool-no="bulb_out"]',
      '[data-field="lights_on"]', '[data-field="lighting_mode"]', '[data-field="lighting.mode"]',
      '[data-field="side_lights"]', '[data-field="dipped_beam"]', '[data-field="low_beam"]', '[data-field="rear_fog"]'
    ];
    selectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => {
        if (node.closest("#openMmiFooterTelltales, .status-strip, footer, .footer, .bottom-bar")) return;
        const host = node.closest(".tile, .footer-item, article, .card") || node;
        host.classList.add("openmmi-telltale-moved-to-footer", "openmmi-light-state-moved-to-footer");
        host.setAttribute("aria-hidden", "true");
      });
    });
  }

  function hideOldFooterItems() {
    const footer = findFooter();
    if (!footer) return;
    footer.querySelectorAll('[data-bool="reverse"], [data-field="reverse"], [data-bool="handbrake"], [data-field="handbrake"], [data-key="handbrake"]').forEach((node) => {
      if (node.closest("#openMmiFooterTelltales")) return;
      const host = node.closest(".footer-item, .status-item, .tile, article, li, div") || node;
      host.classList.add("openmmi-footer-duplicate-hidden");
      host.setAttribute("aria-hidden", "true");
    });
    footer.querySelectorAll(".footer-item, .status-item, .tile, article, li").forEach((node) => {
      if (node.closest("#openMmiFooterTelltales")) return;
      const text = (node.textContent || "").trim().toLowerCase();
      if (/\b(reverse|handbrake|parking brake|park brake|parking|brake)\b/.test(text)) {
        node.classList.add("openmmi-footer-duplicate-hidden");
        node.setAttribute("aria-hidden", "true");
      }
    });
  }

  function updateTestBadge() {
    const footer = findFooter();
    if (!footer) return;
    let badge = footer.querySelector("#openMmiTelltaleTestBadge");
    if (!anyForced()) {
      if (badge) badge.remove();
      document.documentElement.classList.remove("openmmi-telltale-test-active");
      return;
    }
    document.documentElement.classList.add("openmmi-telltale-test-active");
    if (!badge) {
      badge = document.createElement("span");
      badge.id = "openMmiTelltaleTestBadge";
      badge.className = "openmmi-telltale-test-badge";
      footer.appendChild(badge);
    }
    badge.textContent = `TEST ${Array.from(new Set([...FORCED_FROM_URL, ...forcedFromKeyboard])).join(" ")}`;
  }


  const OPENMMI_SETTINGS_KEY = "openmmi.dashboard.settings.v1";
  let openMmiSettingsTelltaleTestActive = false;

  function openMmiReadDashboardPrefs() {
    try {
      return openMmiPrefs.readObject(OPENMMI_SETTINGS_KEY, {});
    } catch (_) {
      return {};
    }
  }

  function openMmiRefreshSettingsTelltaleTest() {
    const prefs = openMmiReadDashboardPrefs();
    openMmiSettingsTelltaleTestActive = String(prefs.telltaleTest || "off").toLowerCase() === "on";
    document.documentElement.classList.toggle("openmmi-telltale-test-active", openMmiSettingsTelltaleTestActive);
  }

  function openMmiApplySettingsTelltaleTestPayload(payload) {
    if (!openMmiSettingsTelltaleTestActive) return payload;

    const next = Object.assign({}, payload || {});
    const state = Object.assign({}, next.state || {});
    const lighting = Object.assign({}, state.lighting || {});
    const vehicle = Object.assign({}, state.vehicle || {});

    // Use broad decoded names so the existing footer renderer can pick up the
    // fields it already understands across old/new payload shapes.
    lighting.lights_on = true;
    lighting.mode = "main_beam_rear_fog";
    lighting.position_lights = true;
    lighting.sidelights = true;
    lighting.low_beam = true;
    lighting.dipped_beam = true;
    lighting.dip_beam = true;
    lighting.high_beam = true;
    lighting.main_beam = true;
    lighting.rear_fog = true;
    lighting.rear_fog_light = true;
    lighting.left_indicator = true;
    lighting.right_indicator = true;
    lighting.indicator_left = true;
    lighting.indicator_right = true;
    lighting.hazard = true;
    lighting.hazards = true;
    lighting.hazard_warning = true;
    lighting.bulb_failure = true;
    lighting.exterior_bulb_failure = true;
    lighting.bulb_out = true;
    lighting.bulb_fault = true;
    lighting.bulb_warning = true;
    lighting.lamp_failure = true;

    vehicle.handbrake = true;
    vehicle.parking_brake = true;
    vehicle.park_brake = true;

    state.lighting = lighting;
    state.vehicle = vehicle;
    next.state = state;
    return next;
  }

  openMmiRefreshSettingsTelltaleTest();
  window.addEventListener("storage", openMmiRefreshSettingsTelltaleTest);
  window.addEventListener("openmmi:settingschange", openMmiRefreshSettingsTelltaleTest);

  function renderStableFooterTelltales(payload) {
    payload = openMmiApplySettingsTelltaleTestPayload(payload);
    lastPayload = payload || lastPayload || {};
    const state = (lastPayload && lastPayload.state) || {};
    const vehicle = state.vehicle || {};
    const lighting = state.lighting || {};
    const strip = ensureStrip();
    if (!strip) return;

    const hazards = lighting.hazards === true || forced("hazard");
    const left = hazards ? true : lighting.left_indicator;
    const right = hazards ? true : lighting.right_indicator;
    const leftForced = forced("left") || forced("hazard");
    const rightForced = forced("right") || forced("hazard");
    const testBlink = anyForced();

    setSlot(strip, "left", left === true, left !== undefined && left !== null, "Left indicator", { forcedBlink: testBlink && leftForced });
    setSlot(strip, "right", right === true, right !== undefined && right !== null, "Right indicator", { forcedBlink: testBlink && rightForced });
    setSlot(strip, "park", vehicle.handbrake === true, vehicle.handbrake !== undefined && vehicle.handbrake !== null, "Parking brake");
    setSlot(strip, "hazard", hazards === true, lighting.hazards !== undefined || forced("hazard"), "Hazard warning", { forcedBlink: testBlink && forced("hazard") });
    setSlot(strip, "bulb", lighting.bulb_out === true, lighting.bulb_out !== undefined && lighting.bulb_out !== null, "Exterior bulb failure");

    setSlot(strip, "sidelights", sideLightsOn(lighting), knownAny(lighting, ["side_lights", "sidelights", "position_lights", "parking_lights"], "sidelights"), "Side/position lights");
    setSlot(strip, "dipped", dippedBeamOn(lighting), knownAny(lighting, ["dipped_beam", "low_beam", "dip_beam", "headlights", "head_lights"], "dipped"), "Dipped beam");
    setSlot(strip, "highbeam", highBeamOn(lighting), knownAny(lighting, ["high_beam", "main_beam", "full_beam"], "highbeam"), "High beam");
    setSlot(strip, "rearfog", rearFogOn(lighting), knownAny(lighting, ["rear_fog", "rear_fog_light", "fog_rear", "fog_lights_rear"], "rearfog"), "Rear fog light");

    hideMovedPageTelltales();
    hideOldFooterItems();
    updateTestBadge();
  }

  function scheduleStableFooterTelltales(payload) {
    lastPayload = payload || lastPayload;
    if (renderRaf) return;
    renderRaf = requestAnimationFrame(() => {
      renderRaf = 0;
      try { renderStableFooterTelltales(lastPayload || {}); }
      catch (error) { console.warn("Open MMI proper light tell-tales failed", error); }
    });
  }

  function refreshAfterForceChange() {
    const currentPayload = openMmiStatusStore.getSnapshot().payload;
    if (currentPayload && typeof render === "function") render(currentPayload);
    else scheduleStableFooterTelltales(lastPayload);
  }

  function toggleForcedToken(token) {
    if (forcedFromKeyboard.has(token)) forcedFromKeyboard.delete(token);
    else forcedFromKeyboard.add(token);
    refreshAfterForceChange();
  }

  document.addEventListener("keydown", (event) => {
    if (!event.altKey || event.ctrlKey || event.metaKey) return;
    const token = KEY_BINDINGS.get(event.key);
    if (!token) return;
    event.preventDefault();
    if (token === "all") {
      ["left", "right", "hazard", "park", "bulb", "sidelights", "dipped", "highbeam", "rearfog"].forEach((item) => forcedFromKeyboard.add(item));
      refreshAfterForceChange();
      return;
    }
    toggleForcedToken(token);
  });

  document.addEventListener("keydown", (event) => {
    if (!event.altKey || event.key.toLowerCase() !== "c") return;
    event.preventDefault();
    forcedFromKeyboard.clear();
    refreshAfterForceChange();
  });

  if (typeof render === "function" && !render.__openMmiProperLightTelltalesWrapped) {
    const previousRender = render;
    render = function renderWithProperLightTelltales(payload) {
      const patched = applyTestOverrides(payload);
      previousRender(patched);
      scheduleStableFooterTelltales(patched);
    };
    render.__openMmiProperLightTelltalesWrapped = true;
  }

  document.addEventListener("DOMContentLoaded", () => scheduleStableFooterTelltales(lastPayload));
  if (document.readyState !== "loading") scheduleStableFooterTelltales(lastPayload);

  window.openMmiRenderFooterTelltales = renderStableFooterTelltales;
  window.openMmiTelltaleTest = {
    toggle: toggleForcedToken,
    clear: () => { forcedFromKeyboard.clear(); refreshAfterForceChange(); },
    active: () => Array.from(new Set([...FORCED_FROM_URL, ...forcedFromKeyboard])),
  };
})();
// --- Open MMI proper light tell-tales end ---

// --- Open MMI V1 roadmap: home/menu navigation start ---
(function openMmiHomeMenuNavigation() {
  if (window.__openMmiHomeMenuNavigationLoaded) return;
  window.__openMmiHomeMenuNavigationLoaded = true;

  const QUICK_PAGES = [
    { id: "pageElectrical", title: "Media", label: "Media" },
    { id: "pageHome", title: "Home", label: "Home" },
    { id: "pageDrive", title: "Drive", label: "Drive" },
  ];
  const MENU_PAGES = {
    climate: { id: "pageClimate", title: "Climate" },
    vehicle: { id: "pageVehicle", title: "Vehicle" },
  };
  const HOME_INDEX = 1;

  const one = (selector) => document.querySelector(selector);
  const many = (selector) => Array.from(document.querySelectorAll(selector));

  function homeFmtNumber(value, digits = 0, fallback = "--") {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return n.toFixed(digits);
  }

  function homeKmhToMph(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "--";
    return Math.round(n * 0.621371).toString();
  }

  function homeText(value, fallback = "--") {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  function ensureHomePage() {
    let page = one("#pageHome");
    if (!page) {
      page = document.createElement("section");
      page.id = "pageHome";
      page.className = "page page-home";
      page.setAttribute("aria-label", "Home menu");

      const firstPage = one(".page");
      if (firstPage && firstPage.parentNode) firstPage.parentNode.insertBefore(page, firstPage);
      else {
        const footer = one("footer.status-strip") || one("footer");
        (footer?.parentNode || document.body).insertBefore(page, footer || null);
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
  }

  function syncQuickArrays() {
    try {
      if (Array.isArray(PAGE_NAMES)) {
        PAGE_NAMES.length = 0;
        QUICK_PAGES.forEach((page) => PAGE_NAMES.push(page.title));
      }
      if (Array.isArray(PAGE_IDS)) {
        PAGE_IDS.length = 0;
        QUICK_PAGES.forEach((page) => PAGE_IDS.push(page.id));
      }
    } catch (_) {}
  }

  function rebuildPager() {
    const pager = one(".pager");
    if (!pager) return;
    pager.innerHTML = QUICK_PAGES.map((page, idx) => `
      <button type="button" data-page="${idx}" aria-label="${page.label}" title="${page.label}"></button>
    `).join("");
    pager.querySelectorAll("button[data-page]").forEach((button) => {
      button.addEventListener("click", () => setPage(Number(button.dataset.page)));
    });
  }

  function setActivePageElement(id) {
    many(".page").forEach((page) => page.classList.toggle("active", page.id === id));
  }

  function setPagerActive(index) {
    many(".pager button").forEach((button, idx) => button.classList.toggle("active", idx === index));
  }

  function showPageById(id, title, quickIndex = HOME_INDEX) {
    setActivePageElement(id);
    setPagerActive(quickIndex);
    const titleEl = one("#pageTitle");
    if (titleEl) titleEl.textContent = title;
    try { activePage = quickIndex; } catch (_) {}
    window.dispatchEvent(new CustomEvent("openmmi:pagechange", { detail: { id, title, quickIndex } }));
  }

  function installNavigationOverride() {
    const nextSetPage = function openMmiSetQuickPage(index) {
      const safeIndex = Number.isFinite(Number(index)) ? Number(index) : HOME_INDEX;
      const idx = ((Math.trunc(safeIndex) % QUICK_PAGES.length) + QUICK_PAGES.length) % QUICK_PAGES.length;
      const page = QUICK_PAGES[idx] || QUICK_PAGES[HOME_INDEX];
      showPageById(page.id, page.title, idx);
    };
    nextSetPage.__openMmiHomeMenu = true;
    try { setPage = nextSetPage; } catch (_) {}
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

  function updateHome(payload) {
    const state = payload?.state || {};
    const vehicle = state.vehicle || {};
    const engine = state.engine || {};
    const fuel = state.fuel || {};
    const lighting = state.lighting || {};

    const speed = one("#homeSpeed");
    if (speed) speed.textContent = homeKmhToMph(vehicle.speed_kmh);

    const rpm = one("#homeRpm");
    if (rpm) rpm.textContent = homeFmtNumber(engine.speed_rpm, 0);

    const range = one("#homeRange");
    if (range) range.textContent = homeKmhToMph(fuel.range_km);

    const lights = one("#homeLights");
    if (lights) lights.textContent = homeText(lighting.mode).replaceAll("_", " ");
  }

  function wrapRenderForHome() {
    try {
      if (typeof render !== "function" || render.__openMmiHomeWrapped) return;
      const previousRender = render;
      const wrapped = function openMmiRenderWithHome(payload) {
        previousRender(payload);
        updateHome(payload);
      };
      wrapped.__openMmiHomeWrapped = true;
      render = wrapped;
    } catch (_) {}
  }

  function bindHomeKey() {
    window.addEventListener("keydown", (event) => {
      const target = event.target;
      if (
        target instanceof Element
        && target.closest("input, textarea, select, [contenteditable='true'], [contenteditable='']")
      ) return;
      if (event.key === "Home" || event.key === "h" || event.key === "H") {
        event.preventDefault();
        setPage(HOME_INDEX);
      }
    });
  }

  ensureHomePage();
  syncQuickArrays();
  rebuildPager();
  installNavigationOverride();
  bindHomeButtons();
  wrapRenderForHome();
  bindHomeKey();
  setPage(HOME_INDEX);
})();
// --- Open MMI V1 roadmap: home/menu navigation end ---

// --- Open MMI V1 roadmap: settings shell start ---
(function openMmiSettingsOptionTree() {
  if (window.__openMmiSettingsOptionTreeLoaded) return;
  window.__openMmiSettingsOptionTreeLoaded = true;

  const one = (selector) => document.querySelector(selector);
  const many = (selector) => Array.from(document.querySelectorAll(selector));
  const state = { section: "units", payload: null };

  function fmt(value, digits = 0, fallback = "--") {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return n.toFixed(digits);
  }

  function text(value, fallback = "--") {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  function boolText(value) {
    if (value === true) return "on";
    if (value === false) return "off";
    return text(value);
  }

  function firstValue(...values) {
    for (const value of values) {
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return undefined;
  }

  function tempText(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return text(value);
    return `${n.toFixed(1)} °C`;
  }

  function voltsText(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return text(value);
    return `${n.toFixed(1)} V`;
  }

  function rpmText(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return text(value);
    return `${Math.round(n)} rpm`;
  }

  function statusParts(payload) {
    const root = payload || {};
    const s = root.state || {};
    const vehicle = s.vehicle || {};
    const lighting = s.lighting || {};
    const climate = s.climate || s.hvac || {};
    const engine = s.engine || {};
    const electrical = s.electrical || s.power || {};
    const media = s.media || {};
    const meta = root.meta || root.status || {};
    const ageValue = root.age_s ?? root.age_seconds ?? meta.age_s ?? meta.age_seconds ?? s.age_s;
    return { root, s, vehicle, lighting, climate, engine, electrical, media, meta, ageValue };
  }

  function pill(label, selected = false) {
    return `<button type="button" class="openmmi-setting-pill${selected ? " is-selected" : ""}">${label}</button>`;
  }

  function row(title, note, controls = "") {
    return `<div class="openmmi-setting-row"><div><strong>${title}</strong><small>${note}</small></div><div class="openmmi-setting-controls">${controls}</div></div>`;
  }

  function metric(label, value) {
    return `<div class="openmmi-settings-metric"><span>${label}</span><strong>${value}</strong></div>`;
  }

  function diagnosticsTemplate(payload) {
    const { vehicle, lighting, climate, engine, electrical, ageValue } = statusParts(payload);
    const lightingText = text(lighting.mode).replaceAll("_", " ");
    const ageText = Number.isFinite(Number(ageValue)) ? `${fmt(ageValue, 1)} s` : "live";
    const outsideDisplay = firstValue(climate.outside_temp_c, climate.outside_c, vehicle.outside_temp_c, vehicle.outside_temperature_c);
    const outsideRaw = firstValue(
      climate.outside_unfiltered_c,
      climate.outside_raw_c,
      climate.raw_outside_temp_c,
      climate.outside_sensor_c,
      vehicle.outside_unfiltered_c,
      vehicle.outside_raw_c
    );
    const coolant = firstValue(engine.coolant_temp_c, engine.coolant_c, vehicle.coolant_temp_c);
    const voltage = firstValue(electrical.voltage_v, electrical.battery_v, vehicle.voltage_v, vehicle.battery_v);
    const rpm = firstValue(engine.rpm, vehicle.rpm);

    return `
      <div class="openmmi-settings-panel-head"><span>Diagnostics</span><small>live decoded state</small></div>
      ${metric("Status age", ageText)}
      ${metric("Lighting mode", lightingText)}
      ${metric("Outside display", tempText(outsideDisplay))}
      ${metric("Outside raw", tempText(outsideRaw))}
      ${metric("Coolant", tempText(coolant))}
      ${metric("Voltage", voltsText(voltage))}
      ${metric("RPM", rpmText(rpm))}
      ${metric("Reverse", boolText(vehicle.reverse ?? vehicle.reverse_selected))}
      ${metric("Handbrake", boolText(vehicle.handbrake ?? vehicle.parking_brake))}
      <a class="openmmi-settings-link" href="/api/status" target="_blank" rel="noreferrer">Open raw /api/status</a>
    `;
  }

  function sectionTemplate(section, payload) {
    const { vehicle } = statusParts(payload);

    if (section === "display") {
      return `
        <div class="openmmi-settings-panel-head"><span>Display</span><small>visual preferences</small></div>
        ${row("Dim mode", "Low-light dashboard theme; Boost raises contrast for bright cabins.", pill("off", true) + pill("on") + pill("boost"))}
        ${row("Reduced animation", "For older tablets or distraction reduction.", pill("off", true) + pill("on"))}
        ${row("Tell-tale test", "Frontend-only icon check; no backend or CAN state changes.", pill("off", true) + pill("on"))}
      `;
    }

    if (section === "diagnostics") {
      return diagnosticsTemplate(payload);
    }

    if (section === "media") {
      return `
        <div class="openmmi-settings-panel-head"><span>Media</span><small>server-side</small></div>
        ${metric("Jellyfin", "env configured")}
        ${row("Token privacy", "Jellyfin URL/token remain server-side, never in browser settings.", pill("locked"))}
        ${row("Media keys", "Browser/system media controls stay handled by the dashboard.", pill("active", true))}
      `;
    }

    if (section === "reverse") {
      return `
        <div class="openmmi-settings-panel-head"><span>Reverse assist</span><small>placeholder</small></div>
        ${row("Reverse popup", "Foundation for a future camera/PDC overlay.", pill("popup", true) + pill("off") + pill("PDC") + pill("camera"))}
        ${row("Auto-dismiss", "Later: hide overlay shortly after leaving reverse.", pill("next"))}
        ${metric("Reverse selected", boolText(vehicle.reverse ?? vehicle.reverse_selected))}
      `;
    }

    return `
      <div class="openmmi-settings-panel-head"><span>Units</span><small>driver display</small></div>
      ${row("Speed", "Dashboard speed and distance display.", pill("mph", true) + pill("km/h"))}
      ${row("Temperature", "Climate and outside temperature display.", pill("°C", true) + pill("°F"))}
`;
  }

  function renderSettingsPanel() {
    const panel = one("#openmmiSettingsPanel");
    if (panel) panel.innerHTML = sectionTemplate(state.section, state.payload);
    openMmiApplyDriverDashboardCleanupV2();

    many("[data-openmmi-settings-section]").forEach((button) => {
      button.classList.toggle("active", button.dataset.openmmiSettingsSection === state.section);
    });
  }

  function ensureSettingsPage() {
    let page = one("#pageSettings");
    if (!page) {
      page = document.createElement("section");
      page.id = "pageSettings";
      page.className = "page page-settings";
      page.setAttribute("aria-label", "Settings");

      const home = one("#pageHome");
      if (home && home.parentNode) home.parentNode.insertBefore(page, home.nextSibling);
      else {
        const footer = one("footer.status-strip") || one("footer");
        (footer?.parentNode || document.body).insertBefore(page, footer || null);
      }
    }

    page.innerHTML = `
      <div class="openmmi-settings-shell">
        <section class="openmmi-settings-sidebar-card" aria-label="Settings categories">
          <div class="openmmi-settings-kicker">V1 roadmap</div>
          <h2>Settings</h2>
          <p>Preferences and diagnostics live here so Drive and Media stay clean.</p>
          <nav class="openmmi-settings-tree" aria-label="Settings tree">
            <button type="button" data-openmmi-settings-section="units">Units <small>mph, °C, raw values</small></button>
            <button type="button" data-openmmi-settings-section="display">Display <small>dim mode, animation</small></button>
            <button type="button" data-openmmi-settings-section="diagnostics">Diagnostics <small>live decoded state</small></button>
            <button type="button" data-openmmi-settings-section="media">Media <small>Jellyfin and keys</small></button>
            <button type="button" data-openmmi-settings-section="reverse">Reverse assist <small>PDC/camera path</small></button>
          </nav>
        </section>
        <section class="openmmi-settings-panel-card" aria-label="Selected settings"><div id="openmmiSettingsStaticControls" class="openmmi-settings-static-controls" hidden></div><div id="openmmiSettingsPanel"></div></section>
      </div>
    `;

    many("[data-openmmi-settings-section]").forEach((button) => {
      button.addEventListener("click", () => {
        state.section = button.dataset.openmmiSettingsSection || "units";
        renderSettingsPanel();
      });
    });

    renderSettingsPanel();
  }

  function showSettingsPage() {
    ensureSettingsPage();
    many(".page").forEach((page) => page.classList.toggle("active", page.id === "pageSettings"));
    many(".pager button").forEach((button, idx) => button.classList.toggle("active", idx === 1));
    const titleEl = one("#pageTitle");
    if (titleEl) titleEl.textContent = "Settings";
    try { activePage = 1; } catch (_) {}
    window.dispatchEvent(new CustomEvent("openmmi:pagechange", { detail: { id: "pageSettings", title: "Settings", quickIndex: 1 } }));
  }

  function bindSettingsButtons() {
    many("[data-openmmi-settings]").forEach((button) => {
      if (button.__openMmiSettingsBound) return;
      button.__openMmiSettingsBound = true;
      button.disabled = false;
      button.classList.remove("openmmi-disabled");
      button.addEventListener("click", showSettingsPage);
    });
  }

  function updateSettings(payload) { state.payload = payload; if (one("#pageSettings.active") && state.section === "diagnostics") renderSettingsPanel(); window.dispatchEvent(new CustomEvent("openmmi:settingsrender")); }

  function wrapRenderForSettings() {
    try {
      if (typeof render !== "function" || render.__openMmiSettingsWrapped) return;
      const previousRender = render;
      const wrapped = function openMmiRenderWithSettings(payload) {
        previousRender(payload);
        updateSettings(payload);
        bindSettingsButtons();
      };
      wrapped.__openMmiSettingsWrapped = true;
      render = wrapped;
    } catch (_) {}
  }

  ensureSettingsPage();
  bindSettingsButtons();
  wrapRenderForSettings();
  window.openMmiShowSettingsPage = showSettingsPage;
  window.addEventListener("openmmi:pagechange", bindSettingsButtons);
})();
// --- Open MMI V1 roadmap: settings shell end ---



// --- Open MMI V1 roadmap: settings wiring v4 stability start ---
(function openMmiSettingsWiringV4Stability() {
  if (window.__openMmiSettingsWiringV4Loaded) return;
  window.__openMmiSettingsWiringV4Loaded = true;

  const STORE_KEY = "openmmi.dashboard.settings.v1";
  const defaults = {
    speedUnit: "mph",
    tempUnit: "c",
    showRaw: false,
    dimMode: false,
    reducedMotion: false,
    reverseAssist: "popup",
  };

  function loadPrefs() {
    try { return Object.assign({}, defaults, openMmiPrefs.readObject(STORE_KEY, {})); }
    catch (_) { return Object.assign({}, defaults); }
  }

  function savePrefs(prefs) {
    try { openMmiPrefs.writeJson(STORE_KEY, prefs); } catch (_) {}
  }

  function setPref(key, value) {
    const prefs = loadPrefs();
    prefs[key] = value;
    savePrefs(prefs);
    applyPrefs();
    requestAnimationFrame(syncSettingsControls);
  }

  function norm(value) {
    return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function currentSection() {
    const active = document.querySelector("[data-openmmi-settings-section].active");
    return active?.dataset?.openmmiSettingsSection || "units";
  }

  function applyPrefs() {
    const prefs = loadPrefs();
    const root = document.documentElement;
    const dimMode = prefs.dimMode === "boost" ? "boost" : (prefs.dimMode ? "on" : "off");
    root.dataset.openmmiDisplayMode = dimMode;
    root.classList.toggle("openmmi-dim-mode", dimMode === "on");
    root.classList.toggle("openmmi-boost-mode", dimMode === "boost");
    root.classList.toggle("openmmi-reduced-motion", !!prefs.reducedMotion);
    root.classList.toggle("openmmi-reverse-assist-off", prefs.reverseAssist === "off");
    window.openMmiDashboardSettings = prefs;
  }

  function setPills(row, selectedLabels) {
    if (!row) return;
    const wanted = new Set([].concat(selectedLabels).map(norm));
    row.querySelectorAll(".openmmi-setting-pill").forEach((pill) => {
      pill.disabled = false;
      const label = norm(pill.textContent);
      const selected = wanted.has(label);
      pill.classList.toggle("is-selected", selected);
      pill.setAttribute("aria-pressed", selected ? "true" : "false");
      pill.setAttribute("role", "button");
      pill.setAttribute("tabindex", "0");
    });
  }

  function rowTitle(row) {
    const strong = row?.querySelector?.("strong");
    return norm(strong ? strong.textContent : row?.textContent);
  }

  function ensureStaticControlsHost() {
    let host = document.querySelector("#openmmiSettingsStaticControls");
    const panel = document.querySelector("#openmmiSettingsPanel");
    if (host || !panel) return host;

    // Runtime fallback for older markup: create the static controls immediately
    // before the live-refreshing panel.
    host = document.createElement("div");
    host.id = "openmmiSettingsStaticControls";
    host.className = "openmmi-settings-static-controls";
    host.hidden = true;
    panel.parentNode.insertBefore(host, panel);
    return host;
  }

  function rawToggleHtml() {
    return '<div class="openmmi-setting-row" data-openmmi-raw-static-row="true"><div><strong>Raw/debug values</strong><small>Show low-level decoded values in this diagnostics panel.</small></div><div class="openmmi-setting-controls"><button type="button" class="openmmi-setting-pill">hide</button><button type="button" class="openmmi-setting-pill">show</button></div></div>';
  }

  function hideRawMetrics(panel, showRaw) {
    panel?.querySelectorAll?.(".openmmi-settings-metric").forEach((metric) => {
      const label = norm(metric.querySelector("span")?.textContent || metric.textContent);
      const rawish = label.includes("outside raw") || label.includes("raw") || label.includes("unfiltered");
      if (rawish) metric.hidden = !showRaw;
    });
  }

  function syncSettingsControls() {
    applyPrefs();
    const prefs = loadPrefs();
    const panel = document.querySelector("#openmmiSettingsPanel");
    const host = ensureStaticControlsHost();


    if (host) {
      if (currentSection() === "diagnostics") {
        host.hidden = false;
        if (!host.querySelector("[data-openmmi-raw-static-row]")) host.innerHTML = rawToggleHtml();
        setPills(host.querySelector("[data-openmmi-raw-static-row]"), prefs.showRaw ? "show" : "hide");
      } else {
        host.hidden = true;
        host.innerHTML = "";
      }
    }

    // Make every visible settings pill interactive and selected without relying
    // on the page being rebuilt.
    panel?.querySelectorAll?.(".openmmi-setting-pill").forEach((pill) => { pill.disabled = false; });
    panel?.querySelectorAll?.(".openmmi-setting-row").forEach((row) => {
      const title = rowTitle(row);
      if (title.includes("speed")) setPills(row, prefs.speedUnit === "kmh" ? "km/h" : "mph");
      else if (title.includes("temperature")) setPills(row, prefs.tempUnit === "f" ? "°f" : "°c");
      else if (title.includes("raw") || title.includes("debug")) setPills(row, prefs.showRaw ? "show" : "hide");
      else if (title.includes("dim")) { const dim = prefs.dimMode === "boost" ? "boost" : (prefs.dimMode ? "on" : "off"); setPills(row, dim); }
      else if (title.includes("reduced")) setPills(row, prefs.reducedMotion ? "on" : "off");
      else if (title.includes("reverse popup")) setPills(row, prefs.reverseAssist);
    });

    hideRawMetrics(panel, prefs.showRaw);
  }

  function handlePill(pill) {
    const row = pill.closest(".openmmi-setting-row");
    if (!row) return;
    const title = rowTitle(row);
    const label = norm(pill.textContent);

    if (title.includes("speed")) setPref("speedUnit", label.includes("km") ? "kmh" : "mph");
    else if (title.includes("temperature")) setPref("tempUnit", label.includes("f") ? "f" : "c");
    else if (title.includes("raw") || title.includes("debug")) setPref("showRaw", label.includes("show"));
    else if (title.includes("dim")) setPref("dimMode", label.includes("boost") ? "boost" : label.includes("on"));
    else if (title.includes("reduced")) setPref("reducedMotion", label.includes("on"));
    else if (title.includes("reverse popup")) {
      if (label.includes("off")) setPref("reverseAssist", "off");
      else if (label.includes("camera")) setPref("reverseAssist", "camera");
      else if (label.includes("pdc")) setPref("reverseAssist", "pdc");
      else setPref("reverseAssist", "popup");
    }
  }

  document.addEventListener("click", (event) => {
    const pill = event.target.closest?.("#openmmiSettingsStaticControls .openmmi-setting-pill, #openmmiSettingsPanel .openmmi-setting-pill");
    if (!pill) return;
    event.preventDefault();
    handlePill(pill);
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const pill = event.target.closest?.("#openmmiSettingsStaticControls .openmmi-setting-pill, #openmmiSettingsPanel .openmmi-setting-pill");
    if (!pill) return;
    event.preventDefault();
    handlePill(pill);
  }, true);

  window.addEventListener("openmmi:settingsrender", () => requestAnimationFrame(syncSettingsControls));
  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(syncSettingsControls));
  document.addEventListener("DOMContentLoaded", () => requestAnimationFrame(syncSettingsControls));

  applyPrefs();
  requestAnimationFrame(syncSettingsControls);
  setTimeout(syncSettingsControls, 100);
})();// --- Open MMI V1 roadmap: settings wiring v4 stability end ---

// --- Open MMI V1 roadmap: settings stable wiring v3 start ---
(function openMmiSettingsStableWiringV3() {
  if (window.__openMmiSettingsStableWiringV3Loaded) return;
  window.__openMmiSettingsStableWiringV3Loaded = true;

  const STORE_KEY = "openmmi.dashboard.settings.v1";
  const defaults = {
    speedUnit: "mph",
    tempUnit: "c",
    showRaw: false,
    dimMode: false,
    reducedMotion: false,
    reverseAssist: "popup",
  };

  function loadPrefs() {
    try {
      return Object.assign({}, defaults, openMmiPrefs.readObject(STORE_KEY, {}));
    } catch (_) {
      return Object.assign({}, defaults);
    }
  }

  function savePrefs(prefs) {
    try { openMmiPrefs.writeJson(STORE_KEY, prefs); } catch (_) {}
  }

  function setPref(key, value) {
    const prefs = loadPrefs();
    prefs[key] = value;
    savePrefs(prefs);
    applyPrefs();
    updateSettingsSelection();
  }

  function norm(value) {
    return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function rowTitle(row) {
    const strong = row?.querySelector?.("strong");
    return norm(strong ? strong.textContent : row?.textContent);
  }

  function currentSection() {
    const active = document.querySelector("[data-openmmi-settings-section].active");
    return active?.dataset?.openmmiSettingsSection || "units";
  }

  function applyPrefs() {
    const prefs = loadPrefs();
    const root = document.documentElement;
    const dimMode = prefs.dimMode === "boost" ? "boost" : (prefs.dimMode ? "on" : "off");
    root.dataset.openmmiDisplayMode = dimMode;
    root.classList.toggle("openmmi-dim-mode", dimMode === "on");
    root.classList.toggle("openmmi-boost-mode", dimMode === "boost");
    root.classList.toggle("openmmi-reduced-motion", !!prefs.reducedMotion);
    root.classList.toggle("openmmi-reverse-assist-off", prefs.reverseAssist === "off");
    window.openMmiDashboardSettings = prefs;
  }

  function setRowSelected(row, selectedLabels) {
    if (!row) return;
    const wanted = new Set([].concat(selectedLabels).map(norm));
    row.querySelectorAll(".openmmi-setting-pill").forEach((pill) => {
      const label = norm(pill.textContent);
      pill.classList.toggle("is-selected", wanted.has(label));
      pill.setAttribute("aria-pressed", wanted.has(label) ? "true" : "false");
      if (!pill.hasAttribute("role")) pill.setAttribute("role", "button");
      if (!pill.hasAttribute("tabindex")) pill.setAttribute("tabindex", "0");
    });
  }

  function updateSettingsSelection() {
    const panel = document.querySelector("#openmmiSettingsPanel");
    if (!panel) return;
    const prefs = loadPrefs();
    panel.querySelectorAll(".openmmi-setting-row").forEach((row) => {
      const title = rowTitle(row);
      if (title.includes("speed")) setRowSelected(row, prefs.speedUnit === "kmh" ? "km/h" : "mph");
      else if (title.includes("temperature")) setRowSelected(row, prefs.tempUnit === "f" ? "°f" : "°c");
      else if (title.includes("raw") || title.includes("debug")) setRowSelected(row, prefs.showRaw ? "show" : "hide");
      else if (title.includes("dim")) { const dim = prefs.dimMode === "boost" ? "boost" : (prefs.dimMode ? "on" : "off"); setRowSelected(row, dim); }
      else if (title.includes("reduced")) setRowSelected(row, prefs.reducedMotion ? "on" : "off");
      else if (title.includes("reverse popup")) setRowSelected(row, prefs.reverseAssist);
    });

    panel.querySelectorAll(".openmmi-settings-metric").forEach((metric) => {
      const label = norm(metric.querySelector("span")?.textContent || metric.textContent);
      const rawish = label.includes("outside raw") || label.includes("raw") || label.includes("unfiltered");
      if (rawish) metric.hidden = !prefs.showRaw;
    });
  }

  function handlePill(pill) {
    const row = pill.closest(".openmmi-setting-row");
    if (!row) return;
    const title = rowTitle(row);
    const label = norm(pill.textContent);
    if (title.includes("speed")) setPref("speedUnit", label.includes("km") ? "kmh" : "mph");
    else if (title.includes("temperature")) setPref("tempUnit", label.includes("f") ? "f" : "c");
    else if (title.includes("raw") || title.includes("debug")) setPref("showRaw", label.includes("show"));
    else if (title.includes("dim")) setPref("dimMode", label.includes("boost") ? "boost" : label.includes("on"));
    else if (title.includes("reduced")) setPref("reducedMotion", label.includes("on"));
    else if (title.includes("reverse popup")) {
      if (label.includes("off")) setPref("reverseAssist", "off");
      else if (label.includes("camera")) setPref("reverseAssist", "camera");
      else if (label.includes("pdc")) setPref("reverseAssist", "pdc");
      else setPref("reverseAssist", "popup");
    }
  }

  document.addEventListener("click", (event) => {
    const pill = event.target.closest?.("#openmmiSettingsPanel .openmmi-setting-pill");
    if (!pill) return;
    event.preventDefault();
    handlePill(pill);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const pill = event.target.closest?.("#openmmiSettingsPanel .openmmi-setting-pill");
    if (!pill) return;
    event.preventDefault();
    handlePill(pill);
  });

  window.addEventListener("openmmi:settingsrender", () => requestAnimationFrame(updateSettingsSelection));
  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(updateSettingsSelection));
  document.addEventListener("DOMContentLoaded", () => {
    applyPrefs();
    requestAnimationFrame(updateSettingsSelection);
  });
  applyPrefs();
  requestAnimationFrame(updateSettingsSelection);
})();
// --- Open MMI V1 roadmap: settings stable wiring v3 end ---

// --- Open MMI V1 roadmap: door overlay start ---
(function openMmiDoorOverlayV1() {
  if (window.__openMmiDoorOverlayV1Loaded) return;
  window.__openMmiDoorOverlayV1Loaded = true;

  const state = {
    currentSignature: "",
    dismissedSignature: "",
  };

  const LABELS = {
    driver: "Driver door",
    driver_door: "Driver door",
    front_left: "Front left door",
    front_left_door: "Front left door",
    passenger: "Passenger door",
    passenger_door: "Passenger door",
    front_right: "Front right door",
    front_right_door: "Front right door",
    rear_left: "Rear left door",
    rear_left_door: "Rear left door",
    rear_right: "Rear right door",
    rear_right_door: "Rear right door",
    boot: "Boot",
    trunk: "Boot",
    tailgate: "Tailgate",
    hatch: "Tailgate",
    bonnet: "Bonnet",
    hood: "Bonnet",
  };

  const one = (selector) => document.querySelector(selector);

  function normaliseKey(key) {
    return String(key || "")
      .trim()
      .toLowerCase()
      .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
      .replace(/[\s\-.]+/g, "_")
      .replace(/^is_/, "")
      .replace(/^door_/, "")
      .replace(/_status$/, "")
      .replace(/_state$/, "")
      .replace(/_ajar$/, "")
      .replace(/_open$/, "")
      .replace(/^open_/, "")
      .replace(/^ajar_/, "");
  }

  function labelFor(path) {
    const normalised = normaliseKey(path);
    if (LABELS[normalised]) return LABELS[normalised];

    const parts = normalised.split("_").filter(Boolean);
    const hasDoorWord = parts.includes("door");
    const joined = parts.filter((part) => part !== "door").join("_");
    if (LABELS[joined]) return LABELS[joined];

    if (normalised.includes("driver")) return "Driver door";
    if (normalised.includes("passenger")) return "Passenger door";
    if (normalised.includes("front_left") || normalised.includes("left_front")) return "Front left door";
    if (normalised.includes("front_right") || normalised.includes("right_front")) return "Front right door";
    if (normalised.includes("rear_left") || normalised.includes("left_rear")) return "Rear left door";
    if (normalised.includes("rear_right") || normalised.includes("right_rear")) return "Rear right door";
    if (normalised.includes("boot") || normalised.includes("trunk")) return "Boot";
    if (normalised.includes("tailgate") || normalised.includes("hatch")) return "Tailgate";
    if (normalised.includes("bonnet") || normalised.includes("hood")) return "Bonnet";

    const readable = parts
      .filter((part) => part && part !== "open" && part !== "ajar" && part !== "status" && part !== "state")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
    return hasDoorWord ? readable : `${readable || "Door"} door`;
  }

  function looksDoorRelated(path) {
    const p = String(path || "").toLowerCase();
    if (/(lock|locked|unlock|window|mirror|seat|module|count)/.test(p)) return false;
    return /(door|boot|trunk|tailgate|hatch|bonnet|hood)/.test(p);
  }

  function isOpenValue(value) {
    if (value === true) return true;
    if (value === false || value === null || value === undefined) return false;
    if (typeof value === "number") return Number.isFinite(value) && value !== 0;
    const text = String(value).trim().toLowerCase();
    if (!text) return false;
    if (["open", "opened", "ajar", "unlatched", "active", "true", "yes", "on", "1"].includes(text)) return true;
    if (["closed", "shut", "latched", "inactive", "false", "no", "off", "0"].includes(text)) return false;
    return /\b(open|ajar|unlatched)\b/.test(text);
  }

  function addDoor(map, label, value) {
    if (!isOpenValue(value)) return;
    map.set(label, true);
  }

  function scanObject(obj, basePath, out) {
    if (!obj || typeof obj !== "object") return;
    if (Array.isArray(obj)) {
      obj.forEach((item, idx) => scanObject(item, `${basePath}[${idx}]`, out));
      return;
    }

    for (const [key, value] of Object.entries(obj)) {
      const path = basePath ? `${basePath}.${key}` : key;
      if (value && typeof value === "object") {
        scanObject(value, path, out);
        continue;
      }
      if (looksDoorRelated(path)) addDoor(out, labelFor(path), value);
    }
  }

  function collectOpenDoors(payload) {
    const root = payload || {};
    const decoded = root.state || root.decoded || root;
    const vehicle = decoded.vehicle || {};
    const body = decoded.body || decoded.comfort || decoded.central_convenience || {};
    const doors = decoded.doors || vehicle.doors || body.doors || {};
    const out = new Map();

    scanObject(doors, "doors", out);
    scanObject(vehicle, "vehicle", out);
    scanObject(body, "body", out);
    scanObject(decoded.doors_status || decoded.door_status || {}, "door_status", out);

    return Array.from(out.keys()).sort((a, b) => a.localeCompare(b));
  }


  function syncDoorOverlayVehicleVisual(overlay) {
    if (!overlay) return;
    const host = overlay.querySelector("#openMmiDoorOverlayCarHost");
    const source = document.querySelector("#carShell");
    if (!host || !source) return;

    let clone = host.querySelector(".car-shell");
    if (!clone) {
      clone = source.cloneNode(true);
      clone.removeAttribute("id");
      clone.classList.add("openmmi-door-overlay-car-shell");
      clone.setAttribute("aria-hidden", "true");
      host.replaceChildren(clone);
    }

    clone.classList.toggle("any-open", source.classList.contains("any-open"));
    clone.querySelectorAll("[data-door-mark]").forEach((mark) => {
      const key = mark.getAttribute("data-door-mark");
      const liveMark = source.querySelector(`[data-door-mark="${key}"]`);
      mark.classList.toggle("open", !!liveMark?.classList.contains("open"));
    });

    const list = overlay.querySelector("#openMmiDoorOverlayList");
    if (list) {
      list.textContent = "";
      list.hidden = true;
      list.setAttribute("aria-hidden", "true");
    }
  }

  function ensureOverlay() {
    let overlay = one("#openMmiVehicleOverlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "openMmiVehicleOverlay";
    overlay.className = "openmmi-vehicle-overlay";
    overlay.setAttribute("aria-live", "polite");
    overlay.setAttribute("hidden", "");
    overlay.innerHTML = `
      <div class="openmmi-vehicle-overlay-card openmmi-door-overlay-visual-card" role="status" aria-label="Door open alert">
        <div class="openmmi-door-overlay-car-host" id="openMmiDoorOverlayCarHost" aria-hidden="true"></div>
        <div class="openmmi-vehicle-overlay-list" id="openMmiDoorOverlayList" hidden aria-hidden="true"></div>
        <button type="button" class="openmmi-vehicle-overlay-dismiss" id="openMmiDoorOverlayDismiss">Dismiss</button>
      </div>
    `;

    const footer = document.querySelector("footer.status-strip") || document.querySelector("footer");
    (footer?.parentNode || document.body).insertBefore(overlay, footer || null);

    syncDoorOverlayVehicleVisual(overlay);

    overlay.querySelector("#openMmiDoorOverlayDismiss")?.addEventListener("click", () => {
      state.dismissedSignature = state.currentSignature;
      hideOverlay();
    });

    return overlay;
  }

  function hideOverlay() {
    const overlay = one("#openMmiVehicleOverlay");
    if (!overlay) return;
    overlay.setAttribute("hidden", "");
    overlay.classList.remove("is-visible");
  }

  function showOverlay(openDoors) {
    const overlay = ensureOverlay();
    const list = overlay.querySelector("#openMmiDoorOverlayList");
    if (list) {
      list.textContent = "";
      list.hidden = true;
      list.setAttribute("aria-hidden", "true");
    }
    overlay.removeAttribute("hidden");
    overlay.classList.add("is-visible");
  }

  function updateDoorOverlay(payload) {
    const openDoors = collectOpenDoors(payload);
    const signature = openDoors.join("|");
    state.currentSignature = signature;

    if (!signature) {
      state.dismissedSignature = "";
      hideOverlay();
      return;
    }

    if (signature === state.dismissedSignature) {
      hideOverlay();
      return;
    }

    showOverlay(openDoors);
  }

  function wrapRenderForDoorOverlay() {
    try {
      if (typeof render !== "function" || render.__openMmiDoorOverlayWrapped) return;
      const previousRender = render;
      const wrapped = function openMmiRenderWithDoorOverlay(payload) {
        previousRender(payload);
        updateDoorOverlay(payload);
      };
      wrapped.__openMmiDoorOverlayWrapped = true;
      render = wrapped;
    } catch (_) {}
  }

  ensureOverlay();
  wrapRenderForDoorOverlay();
  window.openMmiDoorOverlayState = state;
})();
// --- Open MMI V1 roadmap: door overlay end ---

// --- Open MMI V1 roadmap: reverse overlay start ---
(function openMmiReverseOverlayV1() {
  if (window.__openMmiReverseOverlayV1Loaded) return;
  window.__openMmiReverseOverlayV1Loaded = true;

  const state = {
    active: false,
    dismissedThisReverse: false,
  };

  const one = (selector) => document.querySelector(selector);

  function normalText(value) {
    return String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  }

  function truthyReverseValue(value) {
    if (value === true) return true;
    if (value === false || value === null || value === undefined) return false;
    if (typeof value === "number") return Number.isFinite(value) && value !== 0;

    const text = normalText(value);
    if (!text) return false;
    if (["false", "no", "off", "0", "inactive", "not_reverse", "not_reversing", "park", "parking", "neutral", "drive", "d"].includes(text)) return false;
    if (["true", "yes", "on", "1", "active", "reverse", "reversing", "reverse_selected", "r", "gear_r"].includes(text)) return true;
    return /(^|_)(reverse|reversing)(_|$)/.test(text) || text === "r";
  }

  function firstValue(...values) {
    for (const value of values) {
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return undefined;
  }

  function scanForReverse(obj, basePath = "") {
    if (!obj || typeof obj !== "object") return false;
    if (Array.isArray(obj)) return obj.some((item, idx) => scanForReverse(item, `${basePath}[${idx}]`));

    for (const [key, value] of Object.entries(obj)) {
      const path = basePath ? `${basePath}.${key}` : key;
      const p = path.toLowerCase();
      if (value && typeof value === "object") {
        if (scanForReverse(value, path)) return true;
        continue;
      }
      if (/(reverse|reversing|gear|selector|transmission)/.test(p) && !/(assist|overlay|camera|pdc|setting|mode)/.test(p)) {
        if (truthyReverseValue(value)) return true;
      }
    }
    return false;
  }

  function reverseSelected(payload) {
    const root = payload || {};
    const decoded = root.state || root.decoded || root;
    const vehicle = decoded.vehicle || {};
    const drivetrain = decoded.drivetrain || decoded.transmission || decoded.gearbox || {};
    const status = decoded.status || root.status || {};

    const direct = firstValue(
      vehicle.reverse,
      vehicle.reverse_selected,
      vehicle.reverse_gear,
      vehicle.reversing,
      drivetrain.reverse,
      drivetrain.reverse_selected,
      drivetrain.gear,
      drivetrain.selector,
      status.reverse,
      status.reverse_selected,
      decoded.reverse,
      decoded.reverse_selected
    );

    if (truthyReverseValue(direct)) return true;
    if (direct !== undefined && direct !== null && direct !== "") return false;
    return scanForReverse(decoded);
  }

  function ensureOverlay() {
    let overlay = one("#openMmiReverseOverlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "openMmiReverseOverlay";
    overlay.className = "openmmi-reverse-overlay";
    overlay.setAttribute("aria-live", "polite");
    overlay.setAttribute("hidden", "");
    overlay.innerHTML = `
      <div class="openmmi-reverse-overlay-card" role="status" aria-label="Reverse assist alert">
        <div class="openmmi-reverse-overlay-kicker">Reverse assist</div>
        <h2>Reverse selected</h2>
        <p>Camera/PDC overlay placeholder. Rear assist settings will live under Settings → Reverse assist.</p>
        <div class="openmmi-reverse-overlay-grid" aria-hidden="true">
          <span></span><span></span><span></span><span></span>
        </div>
        <button type="button" class="openmmi-reverse-overlay-dismiss" id="openMmiReverseOverlayDismiss">Dismiss</button>
      </div>
    `;

    const footer = document.querySelector("footer.status-strip") || document.querySelector("footer");
    (footer?.parentNode || document.body).insertBefore(overlay, footer || null);

    overlay.querySelector("#openMmiReverseOverlayDismiss")?.addEventListener("click", () => {
      state.dismissedThisReverse = true;
      hideOverlay();
    });

    return overlay;
  }

  function hideOverlay() {
    const overlay = one("#openMmiReverseOverlay");
    if (!overlay) return;
    overlay.setAttribute("hidden", "");
    overlay.classList.remove("is-visible");
  }

  function showOverlay() {
    const overlay = ensureOverlay();
    overlay.removeAttribute("hidden");
    overlay.classList.add("is-visible");
  }

  function updateReverseOverlay(payload) {
    const active = reverseSelected(payload);
    state.active = active;

    if (!active) {
      state.dismissedThisReverse = false;
      hideOverlay();
      return;
    }

    if (state.dismissedThisReverse) {
      hideOverlay();
      return;
    }

    showOverlay();
  }

  function wrapRenderForReverseOverlay() {
    try {
      if (typeof render !== "function" || render.__openMmiReverseOverlayWrapped) return;
      const previousRender = render;
      const wrapped = function openMmiRenderWithReverseOverlay(payload) {
        previousRender(payload);
        updateReverseOverlay(payload);
      };
      wrapped.__openMmiReverseOverlayWrapped = true;
      render = wrapped;
    } catch (_) {}
  }

  ensureOverlay();
  wrapRenderForReverseOverlay();
  window.openMmiReverseOverlayState = state;
})();
// --- Open MMI V1 roadmap: reverse overlay end ---

/* open-mmi dashboard display setting: frontend-only tell-tale visual test */
(function openMmiTellTaleTestSetting() {
  if (window.__openMmiTellTaleTestSettingBound) return;
  window.__openMmiTellTaleTestSettingBound = true;

  const STORE_KEY = "openmmi.dashboard.settings.v1";

  function readPrefs() {
    try {
      return openMmiPrefs.readObject(STORE_KEY, {}) || {};
    } catch (_) {
      return {};
    }
  }

  function writePrefs(prefs) {
    try {
      openMmiPrefs.writeJson(STORE_KEY, prefs);
    } catch (_) {}
  }

  function tellTaleTestEnabled() {
    return readPrefs().telltaleTest === "on";
  }

  function setTellTaleTest(value) {
    const prefs = readPrefs();
    prefs.telltaleTest = value === "on" ? "on" : "off";
    writePrefs(prefs);
    applyTellTaleTest();
    syncTellTaleSettingButtons();
  }

  function icon(src, label, extraClass = "") {
    return `<span class="openmmi-telltale-test-item ${extraClass}" title="${label}" aria-label="${label}" role="img">` +
      `<img src="${src}" alt="" aria-hidden="true" loading="eager" decoding="async" draggable="false">` +
      `<small>${label}</small>` +
      `</span>`;
  }

  function buildStrip() {
    const strip = document.createElement("div");
    strip.id = "openMmiTellTaleTestStrip";
    strip.className = "openmmi-telltale-test-strip";
    strip.setAttribute("role", "status");
    strip.setAttribute("aria-label", "Open MMI frontend tell-tale visual test");
    strip.innerHTML = `
      <span class="openmmi-telltale-test-badge">TEST</span>
      ${icon("icons/telltales/A16L_Left_turn_signal.svg", "Left", "is-green")}
      ${icon("icons/telltales/A16R_Right_turn_signal.svg", "Right", "is-green")}
      ${icon("icons/telltales/A19_Hazard_warning.svg", "Hazard", "is-red")}
      ${icon("icons/telltales/A09_Position_lights.png", "Side", "is-green")}
      ${icon("icons/telltales/A02_Low_Beam_Indicator.png", "Dip", "is-green")}
      ${icon("icons/telltales/A01_High_Beam_Indicator.png", "Main", "is-blue")}
      ${icon("icons/telltales/A06_Rear_fog_light.png", "Rear fog", "is-amber")}
      ${icon("icons/telltales/A14_Exterior_bulb_failure.svg", "Bulb", "is-amber")}
      ${icon("icons/telltales/B02_Parking_brake_indication.svg", "Brake", "is-red")}
    `;
    return strip;
  }

  function footerHost() {
    return document.querySelector("footer.status-strip") || document.querySelector(".status-strip") || document.querySelector("footer");
  }

  function applyTellTaleTest() {
    const enabled = tellTaleTestEnabled();
    document.documentElement.classList.toggle("openmmi-telltale-test-enabled", enabled);
    document.body?.classList.toggle("openmmi-telltale-test-enabled", enabled);

    let strip = document.querySelector("#openMmiTellTaleTestStrip");
    if (!enabled) {
      strip?.remove();
      return;
    }

    const host = footerHost();
    if (!host) return;
    if (!strip) strip = buildStrip();
    if (strip.parentElement !== host) host.appendChild(strip);
  }

  function settingRowFromButton(button) {
    let node = button;
    while (node && node !== document.body) {
      const text = (node.textContent || "").toLowerCase();
      if (text.includes("tell-tale test")) return node;
      node = node.parentElement;
    }
    return null;
  }

  function syncTellTaleSettingButtons() {
    const enabled = tellTaleTestEnabled();
    document.querySelectorAll("#openmmiSettingsPanel button, #openmmiSettingsPanel .openmmi-settings-pill, #openmmiSettingsPanel .openmmi-pill").forEach((button) => {
      const row = settingRowFromButton(button);
      if (!row) return;
      const label = (button.textContent || "").trim().toLowerCase();
      if (label !== "on" && label !== "off") return;
      const active = enabled ? label === "on" : label === "off";
      button.classList.toggle("active", active);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("button, .openmmi-settings-pill, .openmmi-pill");
    if (!button) return;
    const row = settingRowFromButton(button);
    if (!row) {
      setTimeout(syncTellTaleSettingButtons, 0);
      return;
    }
    const label = (button.textContent || "").trim().toLowerCase();
    if (label === "on" || label === "off") setTellTaleTest(label);
  }, true);

  window.openMmiApplyTellTaleTest = applyTellTaleTest;
  window.openMmiSyncTellTaleSettingButtons = syncTellTaleSettingButtons;

  document.addEventListener("DOMContentLoaded", () => {
    applyTellTaleTest();
    syncTellTaleSettingButtons();
  });
  setInterval(() => {
    applyTellTaleTest();
    syncTellTaleSettingButtons();
  }, 750);
})();
/* end open-mmi dashboard display setting: frontend-only tell-tale visual test */

// --- Open MMI V1 roadmap: tell-tale test existing icons v2 start ---
(function openMmiTelltaleTestExistingIconsV2() {
  if (window.__openMmiTelltaleTestExistingIconsV2Loaded) return;
  window.__openMmiTelltaleTestExistingIconsV2Loaded = true;

  const STORE_KEY = "openmmi.dashboard.settings.v1";
  const MODE_KEY = "telltaleTest";

  function readPrefs() {
    try { return openMmiPrefs.readObject(STORE_KEY, {}); }
    catch (_) { return {}; }
  }

  function writePrefs(next) {
    try { openMmiPrefs.writeJson(STORE_KEY, next); } catch (_) {}
  }

  function currentMode() {
    const prefs = readPrefs();
    return String(
      prefs[MODE_KEY] ??
      prefs.tellTaleTest ??
      prefs.telltaleTestMode ??
      "off"
    ).toLowerCase() === "on" ? "on" : "off";
  }

  function testActive() {
    return currentMode() === "on";
  }

  function setMode(mode) {
    const normalised = String(mode).toLowerCase() === "on" ? "on" : "off";
    const prefs = readPrefs();
    prefs[MODE_KEY] = normalised;
    prefs.tellTaleTest = normalised;
    prefs.telltaleTestMode = normalised;
    writePrefs(prefs);
    window.dispatchEvent(new CustomEvent("openmmi:settingschange", { detail: { telltaleTest: normalised } }));
  }

  function removeLegacyVisualTestStrips() {
    document.querySelectorAll([
      "#openMmiTelltaleVisualTestStrip",
      "#openMmiTelltaleTestStrip",
      "#openMmiDisplayTelltaleTestStrip",
      ".openmmi-telltale-visual-test-strip",
      ".openmmi-display-telltale-test-strip",
      ".openmmi-telltale-test-strip"
    ].join(",")).forEach((node) => node.remove());
  }

  function labelBase(slot) {
    return String(slot.getAttribute("aria-label") || slot.getAttribute("title") || "Tell-tale")
      .replace(/:\s*(on|off|test|active|inactive)\s*$/i, "");
  }

  function fallbackSetRealFooterSlots(active) {
    document.documentElement.classList.toggle("openmmi-telltale-test-active", active);
    if (!active) return;

    document.querySelectorAll("#openMmiFooterTelltales [data-openmmi-telltale-slot]").forEach((slot) => {
      const base = labelBase(slot);
      slot.classList.remove("is-inactive");
      slot.classList.add("is-active", "openmmi-test-forced");
      slot.setAttribute("aria-label", `${base}: test`);
      slot.setAttribute("title", `${base}: test`);
      const sr = slot.querySelector(".openmmi-footer-telltale-sr");
      if (sr) sr.textContent = `${base}: test`;
    });
  }

  function applyTelltaleTestMode() {
    const active = testActive();
    removeLegacyVisualTestStrips();

    if (window.openMmiTelltaleTest && typeof window.openMmiTelltaleTest.set === "function") {
      window.openMmiTelltaleTest.set(active);
    } else {
      fallbackSetRealFooterSlots(active);
    }
  }

  function setRowSelected(row, selectedLabel) {
    row.querySelectorAll(".openmmi-setting-pill").forEach((pill) => {
      const label = String(pill.textContent || "").trim().toLowerCase();
      pill.classList.toggle("is-selected", label === selectedLabel);
      pill.setAttribute("aria-pressed", label === selectedLabel ? "true" : "false");
    });
  }

  function ensureSettingsControls() {
    const panel = document.querySelector("#openmmiSettingsPanel");
    if (!panel) return;

    panel.querySelectorAll(".openmmi-setting-row").forEach((row) => {
      const title = String(row.querySelector("strong")?.textContent || "").trim().toLowerCase();
      if (!title.includes("tell-tale") && !title.includes("telltale")) return;

      const controls = row.querySelector(".openmmi-setting-controls");
      if (controls && !controls.querySelector("[data-openmmi-telltale-test-mode]")) {
        controls.innerHTML =
          '<button type="button" class="openmmi-setting-pill" data-openmmi-telltale-test-mode="off">off</button>' +
          '<button type="button" class="openmmi-setting-pill" data-openmmi-telltale-test-mode="on">on</button>';
      }

      const note = row.querySelector("small");
      if (note) note.textContent = "Frontend-only test using the existing footer tell-tale icons.";
      setRowSelected(row, currentMode());
    });
  }

  document.addEventListener("click", (event) => {
    const pill = event.target.closest?.("#openmmiSettingsPanel .openmmi-setting-pill");
    if (!pill) return;

    const row = pill.closest(".openmmi-setting-row");
    const title = String(row?.querySelector("strong")?.textContent || "").trim().toLowerCase();
    if (!title.includes("tell-tale") && !title.includes("telltale")) return;

    event.preventDefault();
    event.stopPropagation();

    const explicit = pill.dataset.openmmiTelltaleTestMode;
    const label = String(explicit || pill.textContent || "").trim().toLowerCase();
    setMode(label === "on" ? "on" : "off");
    ensureSettingsControls();
    applyTelltaleTestMode();
  }, true);

  ["openmmi:settingsrender", "openmmi:pagechange", "openmmi:settingschange"].forEach((name) => {
    window.addEventListener(name, () => {
      requestAnimationFrame(() => {
        ensureSettingsControls();
        applyTelltaleTestMode();
      });
    });
  });

  document.addEventListener("DOMContentLoaded", () => {
    ensureSettingsControls();
    applyTelltaleTestMode();
  });

  // While active, keep any older experimental visual strip out of the DOM and
  // keep the real footer slots forced through the existing tell-tale API.
  setInterval(() => {
    if (testActive()) applyTelltaleTestMode();
    else removeLegacyVisualTestStrips();
  }, 1000);

  ensureSettingsControls();
  applyTelltaleTestMode();
})();
// --- Open MMI V1 roadmap: tell-tale test existing icons v2 end ---

// --- Open MMI V1 roadmap: tell-tale test render-path settings start ---
(function openMmiTelltaleTestRenderPathSettingsV4() {
  if (window.__openMmiTelltaleTestRenderPathSettingsV4Loaded) return;
  window.__openMmiTelltaleTestRenderPathSettingsV4Loaded = true;

  const STORE_KEY = "openmmi.dashboard.settings.v1";

  function readPrefs() {
    try { return openMmiPrefs.readObject(STORE_KEY, {}); }
    catch (_) { return {}; }
  }

  function writePrefs(prefs) {
    try { openMmiPrefs.writeJson(STORE_KEY, prefs); } catch (_) {}
    window.openMmiDashboardSettings = Object.assign({}, window.openMmiDashboardSettings || {}, prefs);
    window.dispatchEvent(new CustomEvent("openmmi:settingschange", { detail: prefs }));
  }

  function rowTitle(row) {
    return (row?.querySelector?.("strong")?.textContent || "").trim().toLowerCase();
  }

  function setSelected(row, selectedLabel) {
    row?.querySelectorAll?.(".openmmi-setting-pill").forEach((button) => {
      const label = (button.textContent || "").trim().toLowerCase();
      button.classList.toggle("is-selected", label === selectedLabel);
      button.classList.remove("openmmi-disabled");
      button.disabled = false;
      button.removeAttribute("disabled");
    });
  }

  function syncTellTaleRow() {
    const prefs = readPrefs();
    const selected = String(prefs.telltaleTest || "off").toLowerCase() === "on" ? "on" : "off";
    document.querySelectorAll("#openmmiSettingsPanel .openmmi-setting-row, #openmmiSettingsStaticControls .openmmi-setting-row").forEach((row) => {
      if (rowTitle(row).includes("tell-tale test")) setSelected(row, selected);
    });
  }

  document.addEventListener("click", (event) => {
    const pill = event.target.closest?.("#openmmiSettingsPanel .openmmi-setting-pill, #openmmiSettingsStaticControls .openmmi-setting-pill");
    if (!pill) return;

    const row = pill.closest(".openmmi-setting-row");
    if (!rowTitle(row).includes("tell-tale test")) return;

    const label = (pill.textContent || "").trim().toLowerCase();
    if (label !== "on" && label !== "off") return;

    event.preventDefault();
    event.stopPropagation();

    const prefs = readPrefs();
    prefs.telltaleTest = label;
    writePrefs(prefs);
    setSelected(row, label);

    const currentPayload = openMmiStatusStore.getSnapshot().payload;
    if (currentPayload && typeof render === "function") {
      try { render(currentPayload); } catch (_) {}
    }
  }, true);

  window.addEventListener("openmmi:settingsrender", () => requestAnimationFrame(syncTellTaleRow));
  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(syncTellTaleRow));
  window.addEventListener("openmmi:settingschange", () => requestAnimationFrame(syncTellTaleRow));
  document.addEventListener("DOMContentLoaded", syncTellTaleRow);
  syncTellTaleRow();
})();
// --- Open MMI V1 roadmap: tell-tale test render-path settings end ---



// --- openmmi door overlay reuse vehicle visual v3 ---

document.addEventListener("DOMContentLoaded", openMmiApplyDriverDashboardCleanupV2);

// --- Open MMI browser performance diagnostics start ---
(function openMmiBrowserPerformanceDiagnostics() {
  if (window.__openMmiBrowserPerformanceDiagnosticsLoaded) return;
  window.__openMmiBrowserPerformanceDiagnosticsLoaded = true;

  const LATEST_KEY = "openmmi.performance.latest.v1";
  const BASELINE_KEY = "openmmi.performance.baseline.v1";
  const STATUS_PATH = "/api/status";
  const STATUS_INTERVAL_MS = 200;
  const SAMPLES_PER_SCENARIO = 50;
  const RUNS_PER_SCENARIO = 5;
  const WARMUP_SAMPLES = 10;
  const SCENARIO_TIMEOUT_MS = 15000;
  const REPORT_SCHEMA = 3;
  const REQUIRED_PASSING_RUNS = 4;
  const SAMPLE_ID = Symbol("openMmiPerformanceSampleId");

  const state = {
    running: false,
    capture: false,
    captureTarget: 0,
    captureAccepted: 0,
    scenario: "",
    sampleSequence: 0,
    samples: [],
    parsedQueue: [],
    inFlight: 0,
    maxInFlight: 0,
    completionOrder: [],
    longTasks: [],
    latest: readJson(LATEST_KEY, null),
    baseline: readJson(BASELINE_KEY, null),
    originalFetch: null,
    originalRender: null,
    longTaskObserver: null,
    visibilityInvalidation: null,
    visibilityHandler: null,
    pageHideHandler: null,
  };

  function readJson(key, fallback) {
    try {
      const value = openMmiPrefs.readJson(key, null);
      return value && typeof value === "object" ? value : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    return openMmiPrefs.writeJson(key, value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function percentile(values, quantile) {
    const data = values
      .map(Number)
      .filter(Number.isFinite)
      .sort((left, right) => left - right);
    if (!data.length) return null;
    if (data.length === 1) return data[0];
    const position = (data.length - 1) * quantile;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return data[lower];
    return data[lower] + (data[upper] - data[lower]) * (position - lower);
  }

  function describe(values) {
    const data = values.map(Number).filter(Number.isFinite);
    if (!data.length) {
      return { count: 0, mean: null, median: null, p95: null, p99: null, maximum: null };
    }
    const mean = data.reduce((sum, value) => sum + value, 0) / data.length;
    return {
      count: data.length,
      mean: round(mean),
      median: round(percentile(data, 0.5)),
      p95: round(percentile(data, 0.95)),
      p99: round(percentile(data, 0.99)),
      maximum: round(Math.max(...data)),
    };
  }

  function round(value) {
    return Number.isFinite(value) ? Math.round(value * 1000) / 1000 : null;
  }

  function sleep(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  async function waitUntil(predicate, timeoutMs, intervalMs = 50) {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      if (state.visibilityInvalidation) return false;
      try {
        if (predicate()) return true;
      } catch (_) {}
      await sleep(intervalMs);
      if (state.visibilityInvalidation) return false;
    }
    return false;
  }

  function activeVisibilityContext() {
    const sampleKey = String(state.scenario || "");
    const match = sampleKey.match(/^(.*)__(setup|warmup|run_(\d+))$/);
    return {
      sample_key: sampleKey || null,
      scenario: match?.[1] || sampleKey || null,
      phase: match?.[2] === "setup"
        ? "setup"
        : match?.[2] === "warmup"
          ? "warmup"
          : match?.[2]
            ? "measured_run"
            : "setup",
      run: match?.[3] ? Number(match[3]) : null,
    };
  }

  function invalidateForVisibility(eventType) {
    if (!state.running || state.visibilityInvalidation) return;
    state.visibilityInvalidation = {
      occurred_at: new Date().toISOString(),
      event: String(eventType || "visibilitychange"),
      visibility_state: document.visibilityState,
      ...activeVisibilityContext(),
    };
    state.capture = false;
    setProgress("Benchmark invalidated — keep this tab visible", 0);
  }

  function installVisibilityGuard() {
    state.visibilityInvalidation = null;
    state.visibilityHandler = () => {
      if (document.hidden) invalidateForVisibility("visibilitychange");
    };
    state.pageHideHandler = () => invalidateForVisibility("pagehide");
    document.addEventListener("visibilitychange", state.visibilityHandler);
    window.addEventListener("pagehide", state.pageHideHandler);
    if (document.hidden) invalidateForVisibility("started_hidden");
  }

  function removeVisibilityGuard() {
    if (state.visibilityHandler) {
      document.removeEventListener("visibilitychange", state.visibilityHandler);
    }
    if (state.pageHideHandler) {
      window.removeEventListener("pagehide", state.pageHideHandler);
    }
    state.visibilityHandler = null;
    state.pageHideHandler = null;
  }

  function throwIfVisibilityInvalidated() {
    if (!state.visibilityInvalidation) return;
    const error = new Error("Benchmark tab lost visibility");
    error.code = "OPENMMI_PERFORMANCE_VISIBILITY_INTERRUPTED";
    throw error;
  }

  function activeSettingsSection() {
    return document.querySelector("[data-openmmi-settings-section].active")
      ?.dataset?.openmmiSettingsSection || "";
  }

  function currentPageId() {
    return document.querySelector(".page.active")?.id || "pageHome";
  }

  function pageIndex(pageId) {
    try {
      return Array.isArray(PAGE_IDS) ? PAGE_IDS.indexOf(pageId) : -1;
    } catch (_) {
      return -1;
    }
  }

  function showPage(pageId) {
    if (pageId === "pageSettings" && typeof window.openMmiShowSettingsPage === "function") {
      window.openMmiShowSettingsPage();
      return true;
    }
    const index = pageIndex(pageId);
    try {
      if (index >= 0 && typeof setPage === "function") {
        setPage(index);
        window.dispatchEvent(
          new CustomEvent("openmmi:pagechange", { detail: { id: pageId } }),
        );
        return true;
      }
    } catch (_) {}
    const page = document.getElementById(pageId);
    if (!page) return false;
    document.querySelectorAll(".page").forEach((candidate) => {
      candidate.classList.toggle("active", candidate === page);
    });
    window.dispatchEvent(
      new CustomEvent("openmmi:pagechange", { detail: { id: pageId } }),
    );
    return true;
  }

  function mediaPageId() {
    return document.querySelector("#openMmiMediaRoot")?.closest(".page")?.id
      || (pageIndex("pageElectrical") >= 0 ? "pageElectrical" : "pageElectrical");
  }

  function activeSourceId() {
    try {
      return window.openMmiMediaSources?.activeSourceId?.()
        || window.openMmiMediaAdapters?.activeSourceId?.()
        || "jellyfin";
    } catch (_) {
      return "jellyfin";
    }
  }

  function sourceEnabled(sourceId) {
    try {
      return Boolean(window.openMmiMediaSources?.isEnabled?.(sourceId));
    } catch (_) {
      return sourceId === "jellyfin";
    }
  }

  async function activateSource(sourceId) {
    const started = performance.now();
    if (!sourceEnabled(sourceId)) {
      return { skipped: true, reason: `${sourceId} is disabled`, setup_ms: null };
    }
    try {
      window.openMmiMediaSources?.setActiveSource?.(sourceId);
      window.openMmiMediaAdapters?.syncActiveSource?.(true);
    } catch (error) {
      return { skipped: true, reason: String(error?.message || error), setup_ms: null };
    }
    showPage(mediaPageId());
    const ready = await waitUntil(() => {
      const root = document.querySelector("#openMmiMediaRoot");
      if (!root) return false;
      const selected = root.dataset.openMmiMediaSource || activeSourceId();
      if (selected !== sourceId) return false;
      if (root.getAttribute("aria-busy") === "true") return false;
      const results = root.querySelector("#ommiMediaResults");
      const realRows = results?.querySelectorAll(
        ".ommi-track:not(.ommi-track-skeleton-v8b), .list-group-item:not(.ommi-track-skeleton-v8b)",
      ).length || 0;
      const message = root.querySelector("#ommiMediaMessage")?.textContent || "";
      return realRows > 0 || /no |ready|tap|error|failed|not configured|could not/i.test(message);
    }, 12000, 75);
    return {
      skipped: false,
      ready,
      setup_ms: round(performance.now() - started),
    };
  }

  function statusUrl(input) {
    try {
      const raw = typeof input === "string" ? input : input?.url;
      if (!raw) return false;
      const parsed = new URL(raw, location.href);
      return parsed.origin === location.origin && parsed.pathname === STATUS_PATH;
    } catch (_) {
      return false;
    }
  }

  function installInstrumentation() {
    if (state.originalFetch || state.originalRender) return;
    state.originalFetch = window.fetch;
    window.fetch = async function openMmiMeasuredFetch(input, init) {
      if (!state.capture || !statusUrl(input)) {
        return state.originalFetch.call(window, input, init);
      }
      if (state.captureAccepted >= state.captureTarget) {
        return state.originalFetch.call(window, input, init);
      }
      state.captureAccepted += 1;
      const sample = {
        id: ++state.sampleSequence,
        scenario: state.scenario,
        started_at_ms: performance.now(),
        response_at_ms: null,
        json_at_ms: null,
        render_start_ms: null,
        render_end_ms: null,
        paint_at_ms: null,
        ok: false,
        error: null,
      };
      state.samples.push(sample);
      state.inFlight += 1;
      sample.in_flight = state.inFlight;
      state.maxInFlight = Math.max(state.maxInFlight, state.inFlight);
      try {
        const response = await state.originalFetch.call(window, input, init);
        sample.response_at_ms = performance.now();
        sample.ok = response.ok;
        const originalJson = response.json.bind(response);
        try {
          Object.defineProperty(response, "json", {
            configurable: true,
            value: async function openMmiMeasuredStatusJson() {
              const payload = await originalJson();
              sample.json_at_ms = performance.now();
              state.parsedQueue.push(sample.id);
              try {
                Object.defineProperty(payload, SAMPLE_ID, {
                  configurable: true,
                  value: sample.id,
                });
              } catch (_) {}
              return payload;
            },
          });
        } catch (_) {}
        return response;
      } catch (error) {
        sample.error = String(error?.message || error);
        throw error;
      } finally {
        state.inFlight = Math.max(0, state.inFlight - 1);
        state.completionOrder.push(sample.id);
      }
    };

    try {
      if (typeof render === "function") {
        state.originalRender = render;
        render = function openMmiMeasuredRender(payload) {
          let sampleId = payload?.[SAMPLE_ID];
          if (sampleId) {
            const queueIndex = state.parsedQueue.indexOf(sampleId);
            if (queueIndex >= 0) state.parsedQueue.splice(queueIndex, 1);
          } else {
            sampleId = state.parsedQueue.shift();
          }
          const sample = state.samples.find((entry) => entry.id === sampleId);
          if (sample && state.capture) sample.render_start_ms = performance.now();
          const result = state.originalRender(payload);
          if (sample && state.capture) {
            sample.render_end_ms = performance.now();
            requestAnimationFrame(() => {
              sample.paint_at_ms = performance.now();
            });
          }
          return result;
        };
      }
    } catch (_) {
      state.originalRender = null;
    }

    try {
      state.longTaskObserver = new PerformanceObserver((list) => {
        if (!state.capture) return;
        for (const entry of list.getEntries()) {
          state.longTasks.push({
            scenario: state.scenario,
            start_ms: round(entry.startTime),
            duration_ms: round(entry.duration),
          });
        }
      });
      state.longTaskObserver.observe({ entryTypes: ["longtask"] });
    } catch (_) {
      state.longTaskObserver = null;
    }
  }

  function removeInstrumentation() {
    state.capture = false;
    if (state.originalFetch) {
      window.fetch = state.originalFetch;
      state.originalFetch = null;
    }
    try {
      if (state.originalRender) render = state.originalRender;
    } catch (_) {}
    state.originalRender = null;
    try {
      state.longTaskObserver?.disconnect();
    } catch (_) {}
    state.longTaskObserver = null;
    state.parsedQueue.length = 0;
  }

  function scenarioSamples(name) {
    return state.samples.filter((sample) => sample.scenario === name);
  }

  function completionDisorder(samples) {
    const wanted = new Set(samples.map((sample) => sample.id));
    let maximum = -Infinity;
    let count = 0;
    for (const id of state.completionOrder) {
      if (!wanted.has(id)) continue;
      if (id < maximum) count += 1;
      maximum = Math.max(maximum, id);
    }
    return count;
  }

  function summariseScenario(name, setup, sampleKey = name) {
    const samples = scenarioSamples(sampleKey);
    const starts = samples.map((sample) => sample.started_at_ms);
    const paints = samples
      .map((sample) => sample.paint_at_ms)
      .filter(Number.isFinite)
      .sort((left, right) => left - right);
    const gaps = (values) => values.slice(1).map((value, index) => value - values[index]);
    const longTasks = state.longTasks.filter((entry) => entry.scenario === sampleKey);
    return {
      name,
      sample_key: sampleKey,
      skipped: Boolean(setup?.skipped),
      skip_reason: setup?.reason || null,
      source_ready: setup?.ready ?? null,
      source_setup_ms: setup?.setup_ms ?? null,
      samples: samples.length,
      successful_requests: samples.filter((sample) => sample.ok && !sample.error).length,
      failed_requests: samples.filter((sample) => sample.error || !sample.ok).length,
      max_in_flight: Math.max(0, ...samples.map((sample) => Number(sample.in_flight) || 0)),
      out_of_order_completions: completionDisorder(samples),
      request_ms: describe(samples.map((sample) =>
        Number.isFinite(sample.response_at_ms)
          ? sample.response_at_ms - sample.started_at_ms
          : NaN,
      )),
      json_ms: describe(samples.map((sample) =>
        Number.isFinite(sample.json_at_ms) && Number.isFinite(sample.response_at_ms)
          ? sample.json_at_ms - sample.response_at_ms
          : NaN,
      )),
      render_cpu_ms: describe(samples.map((sample) =>
        Number.isFinite(sample.render_end_ms) && Number.isFinite(sample.render_start_ms)
          ? sample.render_end_ms - sample.render_start_ms
          : NaN,
      )),
      response_to_paint_ms: describe(samples.map((sample) =>
        Number.isFinite(sample.paint_at_ms) && Number.isFinite(sample.response_at_ms)
          ? sample.paint_at_ms - sample.response_at_ms
          : NaN,
      )),
      request_to_paint_ms: describe(samples.map((sample) =>
        Number.isFinite(sample.paint_at_ms)
          ? sample.paint_at_ms - sample.started_at_ms
          : NaN,
      )),
      request_start_gap_ms: describe(gaps(starts)),
      paint_gap_ms: describe(gaps(paints)),
      long_tasks: {
        supported: Boolean(state.longTaskObserver || longTasks.length),
        count: longTasks.length,
        total_ms: round(longTasks.reduce((sum, entry) => sum + entry.duration_ms, 0)),
        maximum_ms: round(Math.max(0, ...longTasks.map((entry) => entry.duration_ms))),
      },
    };
  }

  async function captureScenarioRun(name, setup, runNumber, targetSamples, warmup = false) {
    const sampleKey = `${name}__${warmup ? "warmup" : `run_${runNumber}`}`;
    const runLabel = warmup ? "warm-up" : `run ${runNumber}/${RUNS_PER_SCENARIO}`;
    setProgress(`Preparing ${name.replaceAll("_", " ")} ${runLabel}…`, 0);
    const setupResult = await setup();
    throwIfVisibilityInvalidated();
    if (setupResult?.skipped) return summariseScenario(name, setupResult, sampleKey);
    await sleep(warmup ? 250 : 350);
    throwIfVisibilityInvalidated();
    const startingCount = scenarioSamples(sampleKey).length;
    state.scenario = sampleKey;
    state.captureTarget = Math.max(0, Number(targetSamples) || 0);
    state.captureAccepted = 0;
    state.capture = true;
    const started = performance.now();
    const completed = await waitUntil(() => {
      const count = scenarioSamples(sampleKey).filter((sample) =>
        Number.isFinite(sample.response_at_ms),
      ).length - startingCount;
      const ratio = Math.min(1, count / targetSamples);
      setProgress(
        `${name.replaceAll("_", " ")} ${runLabel}… ${count}/${targetSamples}`,
        ratio,
      );
      return count >= targetSamples;
    }, SCENARIO_TIMEOUT_MS, 50);
    throwIfVisibilityInvalidated();
    if (state.originalRender) {
      await waitUntil(() => {
        const samples = scenarioSamples(sampleKey).slice(startingCount);
        const completedResponses = samples.filter((sample) => Number.isFinite(sample.response_at_ms)).length;
        const painted = samples.filter((sample) => Number.isFinite(sample.paint_at_ms)).length;
        return painted >= Math.min(completedResponses, targetSamples);
      }, 2000, 25);
      throwIfVisibilityInvalidated();
    }
    state.capture = false;
    state.captureTarget = 0;
    state.captureAccepted = 0;
    throwIfVisibilityInvalidated();
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const summary = summariseScenario(name, setupResult || {}, sampleKey);
    summary.run = warmup ? 0 : runNumber;
    summary.warmup = warmup;
    summary.completed_target = completed;
    summary.capture_ms = round(performance.now() - started);
    return summary;
  }

  function aggregateDistribution(runs, group) {
    const fields = ["mean", "median", "p95", "p99", "maximum"];
    const result = { count: runs.reduce((sum, run) => sum + Number(run?.[group]?.count || 0), 0) };
    for (const field of fields) {
      result[field] = round(percentile(
        runs.map((run) => Number(run?.[group]?.[field])).filter(Number.isFinite),
        0.5,
      ));
    }
    const runP95 = runs.map((run) => Number(run?.[group]?.p95)).filter(Number.isFinite);
    result.worst_p95 = runP95.length ? round(Math.max(...runP95)) : null;
    result.best_p95 = runP95.length ? round(Math.min(...runP95)) : null;
    result.p95_spread = runP95.length
      ? round(Math.max(...runP95) - Math.min(...runP95))
      : null;
    return result;
  }

  function stabilityForScenario(requestStats, paintStats) {
    const requestMedian = Number(requestStats?.p95);
    const requestSpread = Number(requestStats?.p95_spread);
    const paintMedian = Number(paintStats?.p95);
    const paintSpread = Number(paintStats?.p95_spread);
    const requestLimit = Number.isFinite(requestMedian)
      ? Math.max(10, requestMedian * 0.75)
      : null;
    const paintLimit = Number.isFinite(paintMedian)
      ? Math.max(50, paintMedian * 0.25)
      : null;
    const requestStable = !Number.isFinite(requestSpread)
      || !Number.isFinite(requestLimit)
      || requestSpread <= requestLimit;
    const paintStable = !Number.isFinite(paintSpread)
      || !Number.isFinite(paintLimit)
      || paintSpread <= paintLimit;
    return {
      stable: requestStable && paintStable,
      request_p95_spread_ms: round(requestSpread),
      request_p95_spread_limit_ms: round(requestLimit),
      paint_gap_p95_spread_ms: round(paintSpread),
      paint_gap_p95_spread_limit_ms: round(paintLimit),
    };
  }

  function reportIsStable(report) {
    const measured = (report?.scenarios || []).filter((scenario) => !scenario.skipped);
    return Number(report?.schema) === REPORT_SCHEMA
      && measured.length > 0
      && report?.visibility_guard?.remained_visible !== false
      && measured.every((scenario) =>
        scenario.run_count === RUNS_PER_SCENARIO
        && scenario.failed_requests === 0
        && scenario.completed_target
        && scenario.availability?.ready !== false
        && scenario.valid_run_count >= REQUIRED_PASSING_RUNS,
      );
  }


  function aggregateScenario(name, runs, coldSetup = null, skippedSetup = null) {
    if (!runs.length) {
      const summary = summariseScenario(name, skippedSetup || {
        skipped: true,
        reason: "No measured runs completed",
      }, `${name}__none`);
      summary.availability = {
        ready: coldSetup?.ready !== false && !coldSetup?.skipped,
        setup_ms: round(coldSetup?.setup_ms),
        failure_reason: coldSetup?.ready === false
          ? String(coldSetup?.reason || "Source did not become ready")
          : coldSetup?.skipped
            ? String(coldSetup?.reason || "Source was skipped")
            : null,
      };
      summary.benchmark_kind = "cold_activation_only";
      summary.run_count = 0;
      summary.valid_run_count = 0;
      return summary;
    }
    const longTaskCounts = runs.map((run) => Number(run.long_tasks?.count || 0));
    const requestStats = aggregateDistribution(runs, "request_ms");
    const jsonStats = aggregateDistribution(runs, "json_ms");
    const renderStats = aggregateDistribution(runs, "render_cpu_ms");
    const responsePaintStats = aggregateDistribution(runs, "response_to_paint_ms");
    const requestPaintStats = aggregateDistribution(runs, "request_to_paint_ms");
    const requestGapStats = aggregateDistribution(runs, "request_start_gap_ms");
    const paintGapStats = aggregateDistribution(runs, "paint_gap_ms");
    const validRuns = runs.filter((run) =>
      run.completed_target
      && Number(run.failed_requests || 0) === 0
      && Number(run.max_in_flight || 0) <= 1,
    );
    return {
      name,
      benchmark_kind: "cold_activation_plus_five_warm_runs",
      skipped: false,
      skip_reason: null,
      source_ready: coldSetup?.ready !== false,
      source_setup_ms: round(coldSetup?.setup_ms),
      source_setup_worst_ms: round(coldSetup?.setup_ms),
      availability: {
        ready: coldSetup?.ready !== false,
        setup_ms: round(coldSetup?.setup_ms),
        failure_reason: coldSetup?.ready === false
          ? String(coldSetup?.reason || "Source did not become ready")
          : null,
      },
      run_count: runs.length,
      valid_run_count: validRuns.length,
      required_passing_runs: REQUIRED_PASSING_RUNS,
      samples: runs.reduce((sum, run) => sum + Number(run.samples || 0), 0),
      successful_requests: runs.reduce((sum, run) => sum + Number(run.successful_requests || 0), 0),
      failed_requests: runs.reduce((sum, run) => sum + Number(run.failed_requests || 0), 0),
      max_in_flight: Math.max(0, ...runs.map((run) => Number(run.max_in_flight || 0))),
      out_of_order_completions: runs.reduce(
        (sum, run) => sum + Number(run.out_of_order_completions || 0),
        0,
      ),
      request_ms: requestStats,
      json_ms: jsonStats,
      render_cpu_ms: renderStats,
      response_to_paint_ms: responsePaintStats,
      request_to_paint_ms: requestPaintStats,
      request_start_gap_ms: requestGapStats,
      paint_gap_ms: paintGapStats,
      stability: {
        stable: validRuns.length >= REQUIRED_PASSING_RUNS,
        valid_runs: validRuns.length,
        required_runs: REQUIRED_PASSING_RUNS,
      },
      long_tasks: {
        supported: runs.some((run) => run.long_tasks?.supported),
        count: longTaskCounts.reduce((sum, value) => sum + value, 0),
        total_ms: round(runs.reduce((sum, run) => sum + Number(run.long_tasks?.total_ms || 0), 0)),
        maximum_ms: round(Math.max(0, ...runs.map((run) => Number(run.long_tasks?.maximum_ms || 0)))),
      },
      completed_target: validRuns.length >= REQUIRED_PASSING_RUNS,
      capture_ms: round(runs.reduce((sum, run) => sum + Number(run.capture_ms || 0), 0)),
      runs,
    };
  }


  async function benchmarkScenario(name, setup) {
    state.scenario = `${name}__setup`;
    setProgress(`Cold activation: ${name.replaceAll("_", " ")}…`, 0);
    const coldSetup = await setup();
    throwIfVisibilityInvalidated();
    if (coldSetup?.skipped) {
      return aggregateScenario(name, [], coldSetup, coldSetup);
    }
    if (coldSetup?.ready === false) {
      return aggregateScenario(name, [], coldSetup, {
        skipped: false,
        reason: coldSetup?.reason || "Source did not become ready",
      });
    }

    const settledSetup = async () => ({
      skipped: false,
      ready: true,
      setup_ms: 0,
    });
    const warmup = await captureScenarioRun(
      name,
      settledSetup,
      0,
      WARMUP_SAMPLES,
      true,
    );
    if (warmup.skipped) return aggregateScenario(name, [], coldSetup, warmup);

    const runs = [];
    for (let run = 1; run <= RUNS_PER_SCENARIO; run += 1) {
      if (run > 1) await sleep(250);
      const result = await captureScenarioRun(
        name,
        settledSetup,
        run,
        SAMPLES_PER_SCENARIO,
        false,
      );
      throwIfVisibilityInvalidated();
      if (result.skipped) break;
      runs.push(result);
    }
    return aggregateScenario(name, runs, coldSetup);
  }


  function compareMetric(
    baselineScenario,
    candidateScenario,
    group,
    metric,
    allowedRatio,
    absoluteToleranceMs = 0,
  ) {
    const oldValue = Number(baselineScenario?.[group]?.[metric]);
    if (!Number.isFinite(oldValue)) return null;
    const candidateRuns = (candidateScenario?.runs || [])
      .map((run) => Number(run?.[group]?.[metric]))
      .filter(Number.isFinite);
    const baselineRuns = (baselineScenario?.runs || [])
      .map((run) => Number(run?.[group]?.[metric]))
      .filter(Number.isFinite);
    if (baselineRuns.length < REQUIRED_PASSING_RUNS) return null;

    // The acceptance anchor is the slowest baseline run that must pass.
    // With a four-of-five policy this is the fourth-best run, not the median.
    // Small latency values also need an absolute floor: a harmless one- or
    // two-millisecond shift should not look like a large percentage regression.
    const sortedBaselineRuns = [...baselineRuns].sort((left, right) => left - right);
    const baselineAcceptanceAnchor = sortedBaselineRuns[REQUIRED_PASSING_RUNS - 1];
    const relativeLimit = baselineAcceptanceAnchor * (1 + allowedRatio);
    const absoluteLimit = baselineAcceptanceAnchor
      + Math.max(0, Number(absoluteToleranceMs) || 0);
    const limit = Math.max(relativeLimit, absoluteLimit);
    const decisionLimitMs = Math.round(limit);
    const candidateDecisionValues = candidateRuns.map((value) => Math.round(value));
    const baselineDecisionValues = baselineRuns.map((value) => Math.round(value));
    const passedRuns = candidateDecisionValues.filter(
      (value) => value <= decisionLimitMs,
    ).length;
    return {
      baseline: round(oldValue),
      baseline_acceptance_anchor: round(baselineAcceptanceAnchor),
      candidate: round(candidateScenario?.[group]?.[metric]),
      limit: round(limit),
      decision_limit_ms: decisionLimitMs,
      comparison_resolution_ms: 1,
      relative_tolerance: allowedRatio,
      absolute_tolerance_ms: round(absoluteToleranceMs),
      passed_runs: passedRuns,
      measured_runs: candidateRuns.length,
      required_runs: REQUIRED_PASSING_RUNS,
      passed: candidateRuns.length === RUNS_PER_SCENARIO
        && passedRuns >= REQUIRED_PASSING_RUNS,
      baseline_run_values: baselineRuns.map(round),
      candidate_run_values: candidateRuns.map(round),
      baseline_run_decision_values: baselineDecisionValues,
      candidate_run_decision_values: candidateDecisionValues,
    };
  }

  function compareReports(baseline, candidate) {
    if (candidate?.visibility_guard?.remained_visible === false) {
      return {
        passed: null,
        compatible: true,
        category: "visibility",
        reason: "Benchmark tab lost visibility; rerun with this tab kept in the foreground",
        scenarios: [],
      };
    }
    if (!baseline?.scenarios || !candidate?.scenarios) return null;
    const compatible = Number(baseline.schema) === REPORT_SCHEMA
      && Number(baseline.configuration?.runs_per_scenario) === RUNS_PER_SCENARIO
      && Number(baseline.configuration?.samples_per_run) === SAMPLES_PER_SCENARIO
      && Number(baseline.configuration?.warmup_samples) === WARMUP_SAMPLES
      && Number(baseline.configuration?.required_passing_runs) === REQUIRED_PASSING_RUNS;
    if (!compatible) {
      return {
        passed: null,
        compatible: false,
        reason: "The saved baseline uses an older or different benchmark profile. Save a new baseline before judging regressions.",
        scenarios: [],
      };
    }
    const results = [];
    for (const scenario of candidate.scenarios) {
      const old = baseline.scenarios.find((entry) => entry.name === scenario.name);
      if (!old || scenario.skipped || old.skipped) continue;

      if (scenario.availability?.ready === false) {
        results.push({
          name: scenario.name,
          passed: false,
          inconclusive: false,
          category: "availability",
          reason: scenario.availability?.failure_reason || "Source did not become ready",
          checks: {},
        });
        continue;
      }

      const checks = {
        request_p95: compareMetric(old, scenario, "request_ms", "p95", 0.10, 5),
        response_to_paint_p95: compareMetric(old, scenario, "response_to_paint_ms", "p95", 0.10, 5),
        paint_gap_p95: compareMetric(old, scenario, "paint_gap_ms", "p95", 0.20, 0),
      };
      const valid = scenario.valid_run_count >= REQUIRED_PASSING_RUNS
        && scenario.run_count === RUNS_PER_SCENARIO
        && scenario.failed_requests === 0
        && scenario.completed_target;
      const failed = Object.values(checks).filter(Boolean).some((check) => !check.passed)
        || scenario.out_of_order_completions > 0
        || Number(scenario.long_tasks?.maximum_ms || 0) >= 1000;
      results.push({
        name: scenario.name,
        passed: valid ? !failed : null,
        inconclusive: !valid,
        category: valid ? "performance" : "invalid_capture",
        reason: valid
          ? null
          : `Only ${Number(scenario.valid_run_count || 0)} of ${RUNS_PER_SCENARIO} runs were valid`,
        checks,
      });
    }
    const hasFailure = results.some((entry) => entry.passed === false);
    const hasInconclusive = results.some((entry) => entry.passed === null);
    return {
      passed: hasFailure ? false : hasInconclusive ? null : true,
      compatible: true,
      scenarios: results,
    };
  }


  async function runSuite() {
    if (state.running) return;
    state.running = true;
    state.samples = [];
    state.parsedQueue = [];
    state.longTasks = [];
    state.completionOrder = [];
    state.maxInFlight = 0;
    state.sampleSequence = 0;
    installVisibilityGuard();
    const originalPage = currentPageId();
    const originalSource = activeSourceId();
    const audio = document.querySelector("#ommiMediaAudio");
    const interruptedPlayback = Boolean(audio && !audio.paused);
    updateButtons();
    showProgress(true);
    installInstrumentation();

    const report = {
      schema: REPORT_SCHEMA,
      generated_at: new Date().toISOString(),
      label: "browser-automated-suite",
      configuration: {
        status_interval_ms: STATUS_INTERVAL_MS,
        runs_per_scenario: RUNS_PER_SCENARIO,
        samples_per_run: SAMPLES_PER_SCENARIO,
        warmup_samples: WARMUP_SAMPLES,
        scenario_timeout_ms: SCENARIO_TIMEOUT_MS,
        aggregation: "one cold activation plus five warm runs; four-of-five agreement",
        required_passing_runs: REQUIRED_PASSING_RUNS,
      },
      environment: {
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        device_pixel_ratio: window.devicePixelRatio || 1,
        visibility_state: document.visibilityState,
      },
      playback_was_interrupted: interruptedPlayback,
      visibility_guard: {
        required: true,
        remained_visible: true,
        interruptions: [],
      },
      scenarios: [],
    };

    try {
      report.scenarios.push(await benchmarkScenario("home_idle", async () => {
        showPage("pageHome");
        return { skipped: false, ready: true, setup_ms: 0 };
      }));

      if (sourceEnabled("jellyfin")) {
        report.scenarios.push(await benchmarkScenario("media_jellyfin_browse", () =>
          activateSource("jellyfin"),
        ));
      } else {
        report.scenarios.push(aggregateScenario("media_jellyfin_browse", [], null, {
          skipped: true,
          reason: "Jellyfin is disabled",
        }));
      }

      if (sourceEnabled("radio")) {
        report.scenarios.push(await benchmarkScenario("media_radio_browse", () =>
          activateSource("radio"),
        ));
      } else {
        report.scenarios.push(aggregateScenario("media_radio_browse", [], null, {
          skipped: true,
          reason: "Internet Radio is disabled or not acknowledged",
        }));
      }

      report.comparison = compareReports(state.baseline, report);
      state.latest = report;
      writeJson(LATEST_KEY, report);
    } catch (error) {
      if (state.visibilityInvalidation
          || error?.code === "OPENMMI_PERFORMANCE_VISIBILITY_INTERRUPTED") {
        report.visibility_guard.remained_visible = false;
        report.visibility_guard.interruptions = state.visibilityInvalidation
          ? [state.visibilityInvalidation]
          : [];
        report.inconclusive_reason = "Benchmark tab lost visibility";
        report.comparison = compareReports(state.baseline, report) || {
          passed: null,
          compatible: true,
          category: "visibility",
          reason: "Benchmark tab lost visibility; rerun with this tab kept in the foreground",
          scenarios: [],
        };
      } else {
        report.error = String(error?.message || error);
      }
      state.latest = report;
      writeJson(LATEST_KEY, report);
    } finally {
      state.capture = false;
      removeVisibilityGuard();
      removeInstrumentation();
      try {
        if (sourceEnabled(originalSource)) {
          window.openMmiMediaSources?.setActiveSource?.(originalSource);
          window.openMmiMediaAdapters?.syncActiveSource?.(true);
        }
      } catch (_) {}
      showPage(originalPage);
      if (originalPage === "pageSettings") {
        window.openMmiShowSettingsPage?.();
        await sleep(50);
        document.querySelector('[data-openmmi-settings-section="diagnostics"]')?.click();
      }
      state.running = false;
      showProgress(false);
      updateButtons();
      renderReport();
    }
  }

  function formatMs(value) {
    return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} ms` : "—";
  }

  function scenarioCard(scenario) {
    if (scenario.skipped) {
      return `<article class="openmmi-perf-card is-skipped"><strong>${escapeHtml(scenario.name.replaceAll("_", " "))}</strong><span>${escapeHtml(scenario.skip_reason || "Skipped")}</span></article>`;
    }
    const comparison = state.latest?.comparison?.scenarios?.find((entry) => entry.name === scenario.name);
    const badge = comparison
      ? comparison.category === "availability"
        ? '<span class="openmmi-perf-badge is-fail">availability failed</span>'
        : comparison.passed === null
          ? '<span class="openmmi-perf-badge is-warn">inconclusive</span>'
          : `<span class="openmmi-perf-badge ${comparison.passed ? "is-pass" : "is-fail"}">${comparison.passed ? "within baseline" : "regression"}</span>`
      : scenario.availability?.ready === false
        ? '<span class="openmmi-perf-badge is-fail">availability failed</span>'
        : "";
    const method = scenario.run_count
      ? `Cold activation + ${Number(scenario.run_count)} warm runs (${Number(scenario.valid_run_count || 0)} valid)`
      : "Cold activation only";
    const readiness = scenario.availability?.ready === false
      ? escapeHtml(scenario.availability?.failure_reason || "Failed")
      : formatMs(scenario.availability?.setup_ms);
    return `<article class="openmmi-perf-card">
      <header><strong>${escapeHtml(scenario.name.replaceAll("_", " "))}</strong>${badge}</header>
      <p class="openmmi-perf-method">${escapeHtml(method)}</p>
      <dl>
        <div><dt>Status p95</dt><dd>${formatMs(scenario.request_ms?.p95)}</dd></div>
        <div><dt>Response → paint p95</dt><dd>${formatMs(scenario.response_to_paint_ms?.p95)}</dd></div>
        <div><dt>Paint gap p95</dt><dd>${formatMs(scenario.paint_gap_ms?.p95)}</dd></div>
        <div><dt>Cold activation</dt><dd>${readiness}</dd></div>
        <div><dt>Valid warm runs</dt><dd>${Number(scenario.valid_run_count || 0)}/${Number(scenario.run_count || 0)}</dd></div>
        <div><dt>Failures</dt><dd>${Number(scenario.failed_requests || 0)}</dd></div>
        <div><dt>Long tasks</dt><dd>${Number(scenario.long_tasks?.count || 0)}</dd></div>
      </dl>
    </article>`;
  }


  function renderReport() {
    const output = document.querySelector("#openMmiPerformanceResults");
    if (!output) return;
    if (!state.latest) {
      output.innerHTML = '<p class="openmmi-perf-empty">No browser diagnostic run has been recorded yet.</p>';
      return;
    }
    const comparisonText = state.latest.visibility_guard?.remained_visible === false
      ? "Benchmark inconclusive because this tab lost visibility"
      : !state.latest.comparison
        ? "No browser baseline saved"
        : state.latest.comparison.compatible === false
        ? state.latest.comparison.reason
        : state.latest.comparison.scenarios?.some((entry) => entry.category === "availability")
          ? "A source failed its cold activation check"
          : state.latest.comparison.passed === null
            ? "Comparison is inconclusive because fewer than four warm runs were valid"
            : state.latest.comparison.passed
              ? "At least four of five runs are within the saved baseline"
              : "Fewer than four of five runs met the saved baseline";
    output.innerHTML = `
      <div class="openmmi-perf-summary ${state.latest.comparison?.passed === false ? "is-fail" : ""}">
        <strong>${escapeHtml(comparisonText)}</strong>
        <span>${escapeHtml(new Date(state.latest.generated_at).toLocaleString())}</span>
      </div>
      <div class="openmmi-perf-grid">${(state.latest.scenarios || []).map(scenarioCard).join("")}</div>
    `;
  }


  function downloadLatest() {
    if (!state.latest) return;
    const blob = new Blob([`${JSON.stringify(state.latest, null, 2)}\n`], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `open-mmi-browser-performance-${new Date().toISOString().replaceAll(":", "-")}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function saveBaseline() {
    if (!state.latest || !reportIsStable(state.latest)) return;
    state.baseline = typeof structuredClone === "function"
      ? structuredClone(state.latest)
      : JSON.parse(JSON.stringify(state.latest));
    state.baseline.comparison = null;
    writeJson(BASELINE_KEY, state.baseline);
    state.latest.comparison = compareReports(state.baseline, state.latest);
    writeJson(LATEST_KEY, state.latest);
    updateButtons();
    renderReport();
  }

  function clearBaseline() {
    try {
      openMmiPrefs.remove(BASELINE_KEY);
    } catch (_) {}
    state.baseline = null;
    if (state.latest) {
      state.latest.comparison = null;
      writeJson(LATEST_KEY, state.latest);
    }
    updateButtons();
    renderReport();
  }

  function setProgress(label, ratio) {
    const overlay = document.querySelector("#openMmiPerformanceProgress");
    if (!overlay) return;
    const text = overlay.querySelector("[data-openmmi-perf-progress-label]");
    const bar = overlay.querySelector("[data-openmmi-perf-progress-bar]");
    if (text) text.textContent = label;
    if (bar) bar.style.width = `${Math.max(0, Math.min(1, Number(ratio) || 0)) * 100}%`;
  }

  function showProgress(show) {
    const overlay = document.querySelector("#openMmiPerformanceProgress");
    if (!overlay) return;
    overlay.hidden = !show;
    overlay.setAttribute("aria-hidden", show ? "false" : "true");
  }

  function updateButtons() {
    const run = document.querySelector("#openMmiPerformanceRun");
    const download = document.querySelector("#openMmiPerformanceDownload");
    const baseline = document.querySelector("#openMmiPerformanceSaveBaseline");
    const clear = document.querySelector("#openMmiPerformanceClearBaseline");
    if (run) {
      run.disabled = state.running;
      run.textContent = state.running ? "Running…" : "Run robust suite";
    }
    if (download) download.disabled = !state.latest || state.running;
    if (baseline) baseline.disabled = !state.latest || state.running || !reportIsStable(state.latest);
    if (clear) clear.disabled = !state.baseline || state.running;
    const baselineState = document.querySelector("#openMmiPerformanceBaselineState");
    if (baselineState) {
      baselineState.textContent = state.baseline
        ? Number(state.baseline.schema) === REPORT_SCHEMA
          ? `Browser baseline saved ${new Date(state.baseline.generated_at).toLocaleString()}`
          : "Saved baseline uses an older benchmark format"
        : "No browser baseline saved";
    }
  }


  function ensureProgressOverlay() {
    if (document.querySelector("#openMmiPerformanceProgress")) return;
    const overlay = document.createElement("div");
    overlay.id = "openMmiPerformanceProgress";
    overlay.className = "openmmi-performance-progress";
    overlay.hidden = true;
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML = `
      <strong data-openmmi-perf-progress-label>Preparing diagnostics…</strong>
      <div class="openmmi-performance-progress-track"><span data-openmmi-perf-progress-bar></span></div>
      <small>Keep this tab visible. Leaving it invalidates the suite. One cold activation and five warm runs per scenario. Four matching runs are required.</small>
    `;
    document.body.appendChild(overlay);
  }


  function ensurePanel() {
    const page = document.querySelector("#pageSettings");
    const panel = document.querySelector("#openmmiSettingsPanel");
    if (!page || !panel) return;
    let host = document.querySelector("#openMmiSettingsPerformanceHost");
    if (!host) {
      host = document.createElement("section");
      host.id = "openMmiSettingsPerformanceHost";
      host.className = "openmmi-performance-settings";
      host.innerHTML = `
        <header>
          <div><span>Diagnostics</span><h3>Automated browser performance</h3></div>
          <span id="openMmiPerformanceBaselineState" class="openmmi-perf-baseline-state"></span>
        </header>
        <p><strong>Keep this tab visible for the entire run.</strong> Switching tabs, minimising the browser, or navigating away invalidates the suite and prevents baseline saving. Runs Home, Jellyfin browsing, and Internet Radio browsing automatically. Each scenario records one cold activation, then a warm-up and five measured passes. Four of five runs must agree. Allow about three minutes. Radio is tested only when already enabled and privacy-acknowledged. The suite does not start audio; existing playback may stop and will not resume automatically.</p>
        <p class="openmmi-perf-privacy">Results contain timings and scenario names only. Status payloads, telltale values, Jellyfin credentials, station favourites, and search text are not stored or uploaded.</p>
        <div class="openmmi-perf-actions">
          <button type="button" id="openMmiPerformanceRun">Run robust suite</button>
          <button type="button" id="openMmiPerformanceDownload">Download JSON</button>
          <button type="button" id="openMmiPerformanceSaveBaseline">Save as baseline</button>
          <button type="button" id="openMmiPerformanceClearBaseline">Clear baseline</button>
        </div>
        <div id="openMmiPerformanceResults" class="openmmi-performance-results" aria-live="polite"></div>
      `;
      const staticControls = document.querySelector("#openmmiSettingsStaticControls");
      if (staticControls?.parentNode === panel.parentNode) {
        panel.parentNode.insertBefore(host, panel);
      } else {
        panel.parentNode?.insertBefore(host, panel);
      }
      requestAnimationFrame(() => {
        host.scrollIntoView?.({ block: "start", behavior: "auto" });
      });
      host.querySelector("#openMmiPerformanceRun")?.addEventListener("click", runSuite);
      host.querySelector("#openMmiPerformanceDownload")?.addEventListener("click", downloadLatest);
      host.querySelector("#openMmiPerformanceSaveBaseline")?.addEventListener("click", saveBaseline);
      host.querySelector("#openMmiPerformanceClearBaseline")?.addEventListener("click", clearBaseline);
    }
    host.hidden = activeSettingsSection() !== "diagnostics";
    updateButtons();
    renderReport();
  }


  function schedulePanel() {
    requestAnimationFrame(ensurePanel);
  }

  window.addEventListener("openmmi:settingsrender", schedulePanel);
  window.addEventListener("openmmi:pagechange", schedulePanel);
  document.addEventListener("DOMContentLoaded", () => {
    ensureProgressOverlay();
    schedulePanel();
  });
  if (document.readyState !== "loading") {
    ensureProgressOverlay();
    schedulePanel();
  }

  window.openMmiPerformanceDiagnostics = {
    runSuite,
    getLatestReport: () => state.latest,
    getBaseline: () => state.baseline,
    saveLatestAsBaseline: saveBaseline,
  };
})();
// --- Open MMI browser performance diagnostics end ---

// --- Open MMI USB media source start ---
(function openMmiUsbMediaSource() {
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
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "…";
    if (typeof ommiMediaTime === "function") return ommiMediaTime(value);
    const total = Math.max(0, Math.round(value));
    const minutes = Math.floor(total / 60);
    const remainder = String(total % 60).padStart(2, "0");
    return `${minutes}:${remainder}`;
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
        return `/api/usb/browse?${new URLSearchParams({
          dir: state.directoryId || "",
          q: String(query || ""),
          limit: "60",
          filter: filter || "browse",
        })}`;
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
})();
// --- Open MMI USB media source end ---

// --- Open MMI Bluetooth media source start ---
(function openMmiBluetoothMediaSource() {
  if (window.__openMmiBluetoothMediaSourceLoaded) return;
  window.__openMmiBluetoothMediaSourceLoaded = true;

  const state = {
    installed: false,
    pollTimer: null,
    progressTimer: null,
    requestSerial: 0,
    payload: null,
    payloadReceivedAt: 0,
    controlBusy: false,
    playbackOverride: null,
    playbackOverridePosition: 0,
    playbackOverrideStartedAt: 0,
    lastServerPosition: null,
    lastServerObservedAt: 0,
  };

  function adapterApi() {
    return window.openMmiMediaAdapters || null;
  }

  function activeBluetooth() {
    return adapterApi()?.activeSourceId?.() === "bluetooth";
  }

  function bluetoothAdapter() {
    return {
      id: "bluetooth",
      label: "Bluetooth",
      defaultFilter: "now",
      filters: { now: "Now playing" },
      searchPlaceholder: "Bluetooth uses the connected player",
      searchLabel: "Bluetooth media does not support library search",
      emptyText: "No Bluetooth track metadata is available.",
      loadingText: "Checking connected Bluetooth media…",
      readyText: "Controls are sent to the connected Bluetooth player.",
      statusUrl: "/api/bluetooth/status",
      searchUrl() { return "/api/bluetooth/status"; },
      streamUrl() { return ""; },
    };
  }

  function setBluetoothOnlyUi(active) {
    const input = document.querySelector("#ommiMediaSearch");
    input?.closest(".input-group")?.classList.toggle("openmmi-bluetooth-hidden", active);
    document.querySelector("#ommiMediaFilter")?.classList.toggle("openmmi-bluetooth-hidden", active);
    const root = document.querySelector("#openMmiMediaRoot");
    root?.classList.toggle("openmmi-media-source-bluetooth", active);
    const progress = document.querySelector("#ommiMediaProgressTrack");
    if (!active && progress) {
      progress.classList.remove("is-bluetooth-readonly");
      progress.removeAttribute("aria-disabled");
      progress.removeAttribute("title");
    }
    if (!active) return;
    const listTitle = document.querySelector("#ommiMediaListTitle");
    if (listTitle) listTitle.textContent = "Connected Bluetooth player";
  }

  function setButtonState(selector, enabled) {
    const button = document.querySelector(selector);
    if (!button) return;
    button.disabled = !enabled || state.controlBusy;
    button.setAttribute("aria-disabled", String(button.disabled));
  }

  function normalizePlaybackStatus(payload = state.payload) {
    const status = String(payload?.playback_status || "stopped").toLowerCase();
    return ["playing", "paused", "stopped", "forward-seek", "reverse-seek"].includes(status)
      ? status
      : "stopped";
  }

  function effectivePlaybackStatus(payload = state.payload) {
    return state.playbackOverride || normalizePlaybackStatus(payload);
  }

  function rawBluetoothPosition(payload = state.payload) {
    return Math.max(0, Number(payload?.position_seconds || 0));
  }

  function currentBluetoothPosition(payload = state.payload) {
    const duration = Math.max(0, Number(payload?.duration_seconds || 0));
    const overrideStatus = state.playbackOverride;
    let position = overrideStatus
      ? Math.max(0, Number(state.playbackOverridePosition || 0))
      : rawBluetoothPosition(payload);
    if (overrideStatus === "playing") {
      position += Math.max(
        0,
        (performance.now() - Number(state.playbackOverrideStartedAt || performance.now())) / 1000,
      );
    }
    return duration > 0 ? Math.min(duration, position) : position;
  }

  function reconcilePlaybackOverride(payload) {
    const now = performance.now();
    const serverPosition = rawBluetoothPosition(payload);
    const previousPosition = state.lastServerPosition;
    const previousObservedAt = state.lastServerObservedAt;
    state.lastServerPosition = serverPosition;
    state.lastServerObservedAt = now;

    if (!state.playbackOverride) return;
    // Dashboard-issued Bluetooth transport state is authoritative. YouTube and
    // other Android browser players can report both stale Status and a falsely
    // advancing Position while paused, so polls may never release Pause. During
    // an explicit Play state, though, a material Position discontinuity is a
    // useful remote-seek signal and should re-anchor the local elapsed clock.
    if (state.playbackOverride === "playing") {
      const displayedPosition = currentBluetoothPosition(payload);
      const observedSeconds = Math.max(
        0,
        (now - Number(previousObservedAt || now)) / 1000,
      );
      const serverDelta = previousPosition === null
        ? 0
        : serverPosition - Number(previousPosition);
      const drift = serverPosition - displayedPosition;
      const remoteSeek = (
        previousPosition !== null
        && (serverDelta < -1.5 || serverDelta >= observedSeconds + 1.5)
      ) || Math.abs(drift) >= 4;
      if (remoteSeek) {
        state.playbackOverridePosition = serverPosition;
        state.playbackOverrideStartedAt = now;
      }
      return;
    }
    if (state.playbackOverride === "stopped") {
      state.playbackOverridePosition = 0;
    }
  }

  function applyOptimisticControlState(action) {
    const currentStatus = effectivePlaybackStatus(state.payload);
    const currentPosition = currentBluetoothPosition(state.payload);
    let nextStatus = null;
    if (action === "play_pause") {
      nextStatus = ["playing", "forward-seek", "reverse-seek"].includes(currentStatus)
        ? "paused"
        : "playing";
    } else if (["play", "pause", "stop"].includes(action)) {
      nextStatus = action === "play" ? "playing" : action === "pause" ? "paused" : "stopped";
    }
    if (!nextStatus) return;
    state.playbackOverride = nextStatus;
    state.playbackOverridePosition = nextStatus === "stopped" ? 0 : currentPosition;
    state.playbackOverrideStartedAt = performance.now();
    updateTransportUi(state.payload || {});
    updateProgressUi(state.payload || {});
    scheduleProgressTicker();
  }

  function clearProgressTicker() {
    if (state.progressTimer !== null) {
      clearInterval(state.progressTimer);
      state.progressTimer = null;
    }
  }

  function scheduleProgressTicker() {
    clearProgressTicker();
    if (
      !activeBluetooth()
      || document.visibilityState !== "visible"
      || state.playbackOverride !== "playing"
    ) return;
    state.progressTimer = window.setInterval(() => {
      if (
        !activeBluetooth()
        || document.visibilityState !== "visible"
        || state.playbackOverride !== "playing"
      ) {
        clearProgressTicker();
        return;
      }
      updateTransportUi(state.payload || {});
      updateProgressUi(state.payload || {});
    }, 250);
  }

  function updateTransportUi(payload) {
    const controls = payload?.controls || {};
    const playing = ["playing", "forward-seek", "reverse-seek"].includes(
      effectivePlaybackStatus(payload),
    );
    const play = document.querySelector("#ommiMediaPlay");
    if (play) {
      play.innerHTML = typeof ommiMediaIcon === "function"
        ? ommiMediaIcon(playing ? "pause-fill" : "play-fill")
        : (playing ? "Pause" : "Play");
      play.title = playing ? "Pause Bluetooth playback" : "Play Bluetooth media";
      play.setAttribute("aria-label", play.title);
      play.disabled = !controls.play_pause || state.controlBusy;
      play.setAttribute("aria-disabled", String(play.disabled));
    }
    setButtonState("#ommiMediaPrev", controls.previous === true);
    setButtonState("#ommiMediaNext", controls.next === true);
    setButtonState("#ommiMediaStop", controls.stop === true);
  }

  function updateProgressUi(payload) {
    const position = currentBluetoothPosition(payload);
    const duration = Math.max(0, Number(payload?.duration_seconds || 0));
    const percent = duration > 0 ? Math.max(0, Math.min(100, (position / duration) * 100)) : 0;
    const elapsed = document.querySelector("#ommiMediaElapsed");
    const total = document.querySelector("#ommiMediaDuration");
    const fill = document.querySelector("#ommiMediaProgressFill");
    const track = document.querySelector("#ommiMediaProgressTrack");
    if (elapsed) elapsed.textContent = typeof ommiMediaTime === "function" ? ommiMediaTime(position) : "0:00";
    if (total) total.textContent = typeof ommiMediaTime === "function" ? ommiMediaTime(duration) : "0:00";
    if (fill) fill.style.width = `${percent}%`;
    if (track) {
      track.classList.add("is-bluetooth-readonly");
      track.setAttribute("aria-valuenow", String(Math.round(percent)));
      track.setAttribute("aria-disabled", "true");
      track.title = "Seeking is not exposed by BlueZ Bluetooth media control";
    }
  }

  function renderPayload(payload) {
    if (!activeBluetooth()) return;
    state.payload = payload || {};
    state.payloadReceivedAt = performance.now();
    reconcilePlaybackOverride(state.payload);
    setBluetoothOnlyUi(true);
    const remote = document.querySelector("#ommiMediaRemoteState");
    if (remote) {
      remote.textContent = String(payload?.state_label || payload?.status || "unavailable").toUpperCase();
      remote.title = String(payload?.subtitle || "");
    }

    if (!payload?.available) {
      state.playbackOverride = null;
      state.playbackOverridePosition = 0;
      openMmiMedia.queue = [];
      openMmiMedia.current = null;
      openMmiMedia.index = -1;
      ommiMediaRenderResults([]);
      const title = document.querySelector("#ommiMediaTitle");
      const subtitle = document.querySelector("#ommiMediaSubtitle");
      if (title) title.textContent = "Connect Bluetooth audio";
      if (subtitle) subtitle.textContent = String(payload?.subtitle || "No remote media player was found");
      if (typeof ommiMediaSetArtwork === "function") ommiMediaSetArtwork(null);
      ommiMediaSetMessage(String(payload?.subtitle || "Bluetooth media is unavailable"), payload?.status === "error" ? "error" : "");
      updateTransportUi(payload);
      updateProgressUi(payload);
      scheduleProgressTicker();
      return;
    }

    const item = payload.track || null;
    if (item) {
      ommiMediaRenderResults([item]);
      openMmiMedia.index = 0;
      openMmiMedia.current = openMmiMedia.queue[0] || item;
      ommiMediaSetNowPlaying(openMmiMedia.current);
      document.querySelector('[data-open-mmi-track="0"]')?.classList.add("is-playing", "active");
    } else {
      ommiMediaRenderResults([]);
      openMmiMedia.index = -1;
      openMmiMedia.current = null;
      const title = document.querySelector("#ommiMediaTitle");
      const subtitle = document.querySelector("#ommiMediaSubtitle");
      if (title) title.textContent = String(payload.device_name || "Bluetooth device");
      if (subtitle) subtitle.textContent = String(payload.player_name || "Connected remote media player");
      if (typeof ommiMediaSetArtwork === "function") ommiMediaSetArtwork(null);
    }
    ommiMediaSetMessage(
      item
        ? `${payload.device_name || "Bluetooth device"} · controls stay on the connected player`
        : "Connected; start media on the Bluetooth device to show track details.",
    );
    updateTransportUi(payload);
    updateProgressUi(payload);
    scheduleProgressTicker();
    if (typeof ommiMediaFitViewport === "function") ommiMediaFitViewport();
  }

  function clearPoll() {
    if (state.pollTimer !== null) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function schedulePoll(delay = 1000) {
    clearPoll();
    if (!activeBluetooth() || document.visibilityState !== "visible") return;
    state.pollTimer = window.setTimeout(() => refresh(false), delay);
  }

  async function refresh(showLoading = false) {
    clearPoll();
    if (!activeBluetooth()) {
      setBluetoothOnlyUi(false);
      return;
    }
    const serial = ++state.requestSerial;
    adapterApi()?.applySourceUi?.(adapterApi()?.adapters?.bluetooth);
    setBluetoothOnlyUi(true);
    if (showLoading) {
      ommiMediaSetMessage("Checking connected Bluetooth media…");
      ommiMediaSetLoading(true);
    }
    try {
      const payload = await ommiMediaFetchJson("/api/bluetooth/status");
      if (serial !== state.requestSerial || !activeBluetooth()) return;
      renderPayload(payload);
    } catch (error) {
      if (serial !== state.requestSerial || !activeBluetooth()) return;
      renderPayload({
        configured: false,
        available: false,
        status: "error",
        state_label: "error",
        subtitle: `Bluetooth status failed: ${error.message}`,
        controls: {},
      });
    } finally {
      if (serial === state.requestSerial && showLoading) ommiMediaSetLoading(false);
      if (serial === state.requestSerial) schedulePoll(1000);
    }
  }

  function bluetoothPlayButtonAction() {
    const status = effectivePlaybackStatus(state.payload);
    return ["playing", "forward-seek", "reverse-seek"].includes(status)
      ? "pause"
      : "play";
  }

  async function sendControl(action) {
    if (!activeBluetooth() || state.controlBusy) return;
    const playerId = state.payload?.player_id;
    if (!playerId) {
      ommiMediaSetMessage("No Bluetooth media player is connected.", "error");
      return;
    }
    state.controlBusy = true;
    updateTransportUi(state.payload);
    try {
      const result = await openMmiApiClient.postJson(
        "/api/bluetooth/control",
        { player_id: playerId, action },
        { allowInvalidJson: true, includeResponse: true, requireOk: false },
      );
      const response = result.response;
      const payload = result.payload || {};
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.error || `HTTP ${response.status}`);
      }
      const performedAction = String(payload?.performed_action || action).toLowerCase();
      if (payload?.playback_status) {
        state.payload = {
          ...(state.payload || {}),
          playback_status: String(payload.playback_status).toLowerCase(),
        };
      }
      applyOptimisticControlState(performedAction);
      ommiMediaSetMessage(`Bluetooth ${performedAction.replace("_", " ")} sent.`);
    } catch (error) {
      ommiMediaSetMessage(`Bluetooth control failed: ${error.message}`, "error");
    } finally {
      state.controlBusy = false;
      window.setTimeout(() => refresh(false), 350);
    }
  }

  function bindCaptureControls() {
    const root = document.querySelector("#openMmiMediaRoot");
    if (!root || root.dataset.openMmiBluetoothBound === "true") return;
    root.dataset.openMmiBluetoothBound = "true";
    root.addEventListener("click", (event) => {
      if (!activeBluetooth()) return;
      let action = null;
      if (event.target.closest?.("#ommiMediaPlay")) action = bluetoothPlayButtonAction();
      else if (event.target.closest?.("#ommiMediaPrev")) action = "previous";
      else if (event.target.closest?.("#ommiMediaNext")) action = "next";
      else if (event.target.closest?.("#ommiMediaStop")) action = "stop";
      else if (event.target.closest?.("[data-open-mmi-track]")) action = "play";
      else if (event.target.closest?.("#ommiMediaProgressTrack")) {
        event.preventDefault();
        event.stopImmediatePropagation();
        ommiMediaSetMessage("Bluetooth seeking is not exposed by BlueZ.");
        return;
      }
      if (!action) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      sendControl(action);
    }, true);
  }

  function patchMediaFunctions() {
    if (state.installed) return;
    const api = adapterApi();
    if (!api?.adapters || typeof ommiMediaLoadLibrary !== "function") return;
    api.adapters.bluetooth = bluetoothAdapter();

    const originalLoadLibrary = ommiMediaLoadLibrary;
    ommiMediaLoadLibrary = function ommiMediaLoadBluetoothAware(query = "", filter = openMmiMedia.filter) {
      if (!activeBluetooth()) {
        setBluetoothOnlyUi(false);
        return originalLoadLibrary(query, filter);
      }
      return refresh(true);
    };

    const originalRefreshStatus = ommiMediaRefreshStatus;
    ommiMediaRefreshStatus = function ommiMediaRefreshBluetoothAware() {
      if (!activeBluetooth()) {
        setBluetoothOnlyUi(false);
        return originalRefreshStatus();
      }
      return refresh(false);
    };

    const originalPlayIndex = ommiMediaPlayIndex;
    ommiMediaPlayIndex = function ommiMediaPlayBluetoothAware(index) {
      if (!activeBluetooth()) return originalPlayIndex(index);
      return sendControl("play");
    };

    if (typeof ommiMediaPrev === "function") {
      const originalPrev = ommiMediaPrev;
      ommiMediaPrev = function ommiMediaPreviousBluetoothAware() {
        return activeBluetooth() ? sendControl("previous") : originalPrev();
      };
    }
    if (typeof ommiMediaNext === "function") {
      const originalNext = ommiMediaNext;
      ommiMediaNext = function ommiMediaNextBluetoothAware() {
        return activeBluetooth() ? sendControl("next") : originalNext();
      };
    }
    if (typeof ommiMediaUpdateProgress === "function") {
      const originalUpdateProgress = ommiMediaUpdateProgress;
      ommiMediaUpdateProgress = function ommiMediaProgressBluetoothAware() {
        if (!activeBluetooth()) return originalUpdateProgress();
        updateProgressUi(state.payload || {});
      };
    }
    if (typeof ommiMediaUpdatePlayState === "function") {
      const originalUpdatePlayState = ommiMediaUpdatePlayState;
      ommiMediaUpdatePlayState = function ommiMediaPlayStateBluetoothAware() {
        if (!activeBluetooth()) return originalUpdatePlayState();
        updateTransportUi(state.payload || {});
      };
    }

    state.installed = true;
    bindCaptureControls();
    try { api.syncActiveSource?.(true); } catch (_) {}
  }

  function syncPresence() {
    const active = activeBluetooth();
    setBluetoothOnlyUi(active);
    if (active) refresh(false);
    else {
      state.requestSerial += 1;
      state.payload = null;
      state.playbackOverride = null;
      state.playbackOverridePosition = 0;
      state.lastServerPosition = null;
      clearPoll();
      clearProgressTicker();
    }
  }

  function install() {
    if (!adapterApi()?.adapters || typeof ommiMediaLoadLibrary !== "function") {
      setTimeout(install, 25);
      return;
    }
    patchMediaFunctions();
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest?.(
      "[data-openmmi-media-source], [data-openmmi-media-source-enable], [data-openmmi-media-default-source]",
    )) {
      requestAnimationFrame(syncPresence);
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && activeBluetooth()) {
      refresh(false);
      scheduleProgressTicker();
    } else {
      clearPoll();
      clearProgressTicker();
    }
  });
  window.addEventListener("openmmi:pagechange", () => requestAnimationFrame(syncPresence));
  document.addEventListener("DOMContentLoaded", install);
  install();

  window.openMmiBluetoothMedia = {
    state,
    refresh: () => refresh(false),
    control: sendControl,
  };
})();
// --- Open MMI Bluetooth media source end ---
