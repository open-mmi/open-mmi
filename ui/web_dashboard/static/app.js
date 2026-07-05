const PAGE_NAMES = ["Drive", "Climate", "Vehicle", "Engine / Electrical"];
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
