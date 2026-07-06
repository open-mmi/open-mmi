const PAGE_NAMES = ["Drive", "Climate", "Vehicle", "Media"];
const PAGE_IDS = ["pageDrive", "pageClimate", "pageVehicle", "pageElectrical"];
const DOORS = ["front_left", "front_right", "rear_left", "rear_right", "boot", "bonnet"];

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

  setField("speed_mph", kmToMi(vehicle.speed_kmh, 0));
  setField("rpm", fmtNum(engine.speed_rpm, 0));
  setField("odo_mi", kmToMi(vehicle.odometer_km, 0));
  setField("range_mi", kmToMi(fuel.range_km_candidate ?? fuel.range_km_rounded_candidate, 0));
  setField("coolant_c", fmtNum(engine.coolant_temp_c, 0));
  setField("outside_reg_c", fmtNum(climate.outside_temp_regulation_c, 1));
  setField("outside_unfiltered_c", fmtNum(climate.outside_temp_unfiltered_c, 1));
  setField("voltage_v", fmtNum(electrical.supply_voltage_v ?? electrical.terminal30_voltage_v, 1));
  setField("blower_pct", fmtNum(climate.blower_load_percent, 1));
  setField("dimmer_pct", fmtNum(lighting.dimmer_percent ?? lighting.dimmer_percent_mirror, 0));
  setField("lighting_mode", lighting.mode || "--");
  setField("lights_on", lightsLabel(lighting.lights_on));
  setField("indicators", indicatorLabel(lighting));
  setField("air_intake", climate.air_intake || "Normal");

  setBool("handbrake", vehicle.handbrake);
  setBool("reverse", vehicle.reverse);
  setBool("rear_heater", climate.rear_window_heater_requested);
  setBool("front_demist", climate.front_demist_air_request);
  setBool("compressor", climate.compressor_active);
  setBool("hazards", lighting.hazards);
  setBoolNo("bulb_out", lighting.bulb_out);

  DOORS.forEach((name) => updateDoor(name, doors[name]));
  $("#carShell")?.classList.toggle("any-open", doors.any_open === true);

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
      bar.setAttribute('title', 'Coolant temperature: ' + tempC.toFixed(0) + ' °C');
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

async function fetchStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    render(await response.json());
  } catch (err) {
    updateHealth({ health: { status: "error", age_seconds: null } });
  }
}

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
  fetchStatus();
  setInterval(fetchStatus, 500);
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
  ommiMediaBind();
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
            <div id="ommiMediaArt" class="ommi-art flex-shrink-0" aria-hidden="true"><span>${ommiMediaIcon("music-note-beamed", "ommi-art-icon")}</span></div>
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
    art.innerHTML = `<span>${ommiMediaIcon("music-note-beamed", "ommi-art-icon")}</span>`;
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
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
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
      <span class="ommi-track-art">${item.image_url ? `<img src="${ommiMediaEsc(item.image_url)}" alt="">` : ommiMediaIcon("music-note-beamed")}</span>
      <span class="ommi-track-copy"><strong>${ommiMediaEsc(item.name || "Untitled")}</strong><small>${ommiMediaEsc([item.artist, item.album].filter(Boolean).join(" · ") || "Unknown artist")}</small></span>
      <span class="ommi-track-duration">${ommiMediaTime(item.duration_seconds)}</span>
    </button>`).join("");
}

async function ommiMediaLoadLibrary(query = "") {
  ommiMediaPage();
  const listTitle = document.querySelector("#ommiMediaListTitle");
  const q = String(query || "").trim();
  openMmiMedia.lastQuery = q;
  if (listTitle) listTitle.textContent = q ? "Search results" : "Recent music";
  ommiMediaSetMessage(q ? "Searching…" : "Loading music…");
  try {
    const payload = await ommiMediaFetchJson(`/api/jellyfin/search?q=${encodeURIComponent(q)}&limit=60`);
    if (payload.error) ommiMediaSetMessage(payload.error, "error");
    else ommiMediaSetMessage("Tap any track to play locally.");
    ommiMediaRenderResults(payload.items || []);
  } catch (err) {
    ommiMediaSetMessage(`Could not load library: ${err.message}`, "error");
    ommiMediaRenderResults([]);
  }
  ommiMediaFitViewport();
}

async function ommiMediaRefreshStatus() {
  ommiMediaPage();
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

  root.addEventListener("click", async (event) => {
    const trackButton = event.target.closest?.("[data-open-mmi-track]");
    if (trackButton) {
      event.preventDefault();
      await ommiMediaPlayIndex(trackButton.dataset.openMmiTrack);
      return;
    }
    if (event.target.closest?.("#ommiMediaSearchBtn")) return ommiMediaLoadLibrary(document.querySelector("#ommiMediaSearch")?.value || "");
    if (event.target.closest?.("#ommiMediaRecentBtn")) {
      const input = document.querySelector("#ommiMediaSearch");
      if (input) input.value = "";
      return ommiMediaLoadLibrary("");
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
    if (event.key === "Enter" && event.target?.id === "ommiMediaSearch") ommiMediaLoadLibrary(event.target.value || "");
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

function ommiMediaBoot() {
  ommiMediaPage();
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

