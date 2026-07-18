(function openMmiRuntimeDiagnosticsModule(root, factory) {
  const moduleApi = factory(root);
  if (typeof module === "object" && module.exports) module.exports = moduleApi;
  if (root) root.openMmiRuntimeDiagnostics = moduleApi;
})(typeof globalThis !== "undefined" ? globalThis : this, function createRuntimeDiagnosticsModule(root) {
  "use strict";

  const ENDPOINT = "/api/system/diagnostics/runtime";
  const DEFAULT_INTERVAL_MS = 3000;
  const REQUIRED_CONSTRAINED_SAMPLES = 2;

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatNumber(value, digits = 0, suffix = "") {
    const parsed = number(value);
    return parsed === null ? "--" : `${parsed.toFixed(digits)}${suffix}`;
  }

  function yesNo(value) {
    if (value === true) return "Yes";
    if (value === false) return "No";
    return "--";
  }

  function escapeHtml(value) {
    return String(value ?? "--")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function thermalLabel(state) {
    return {
      unavailable: "Unavailable",
      "temperature-only": "Temperature available",
      normal: "Normal",
      warm: "Warm",
      "thermal-limit-active": "Thermal limit active",
      hot: "Hot",
      critical: "Critical",
    }[state] || "Unavailable";
  }

  function chargingLabel(power = {}) {
    const state = power.charging_state;
    if (state === "on-battery") return "On battery";
    if (state === "charging") return "AC connected — charging";
    if (state === "full") return "AC connected — full";
    if (state === "not-charging") return "AC connected — not charging";
    if (state === "ac-connected") return "AC connected";
    return "Unknown";
  }

  function deriveSystemState(sample = {}, constrainedSamples = 0) {
    const thermal = sample.thermal || {};
    const thermalState = thermal.summary || "unavailable";
    const confirmedConstraint = constrainedSamples >= REQUIRED_CONSTRAINED_SAMPLES;
    const thermalActive = ["thermal-limit-active", "hot", "critical"].includes(thermalState);

    if (thermalState === "critical") return { code: "critical", label: "Critical temperature", level: "danger" };
    if (confirmedConstraint && thermalActive) {
      return { code: "performance-limited-temperature", label: "Performance limited by temperature", level: "danger" };
    }
    if (thermalState === "hot") return { code: "hot", label: "Hot", level: "danger" };
    if (thermalActive) return { code: "thermal-limit-active", label: "Thermal limit active", level: "warning" };
    if (confirmedConstraint) return { code: "clock-constrained", label: "Clock constrained under load", level: "warning" };
    if (thermalState === "warm") return { code: "warm", label: "Warm", level: "warning" };
    if (thermalState === "unavailable" && !sample.cpu?.cpus?.length && !sample.power?.supplies?.length) {
      return { code: "unavailable", label: "Unavailable", level: "neutral" };
    }
    return { code: "normal", label: "Normal", level: "normal" };
  }

  function updateHistory(history, sample = {}) {
    const next = Object.assign({
      cpuMinMhz: null,
      cpuMaxMhz: null,
      tempMinC: null,
      tempMaxC: null,
    }, history || {});
    const currentMin = number(sample.cpu?.current_min_mhz);
    const currentMax = number(sample.cpu?.current_max_mhz);
    const temperature = number(sample.thermal?.temperature_c);
    if (currentMin !== null) next.cpuMinMhz = next.cpuMinMhz === null ? currentMin : Math.min(next.cpuMinMhz, currentMin);
    if (currentMax !== null) next.cpuMaxMhz = next.cpuMaxMhz === null ? currentMax : Math.max(next.cpuMaxMhz, currentMax);
    if (temperature !== null) next.tempMinC = next.tempMinC === null ? temperature : Math.min(next.tempMinC, temperature);
    if (temperature !== null) next.tempMaxC = next.tempMaxC === null ? temperature : Math.max(next.tempMaxC, temperature);
    return next;
  }

  function relevantTripText(thermal = {}) {
    const trip = thermal.relevant_trip;
    if (!trip || number(trip.temperature_c) === null) return "--";
    const types = Array.isArray(trip.types) && trip.types.length ? ` ${trip.types.join("/")}` : "";
    return `${formatNumber(trip.temperature_c, 1, " °C")}${types}`;
  }

  function batteryText(power = {}) {
    const capacity = number(power.capacity_percent);
    const status = power.battery_status || chargingLabel(power);
    if (capacity === null) return status || "--";
    return `${Math.round(capacity)}% — ${status || "Unknown"}`;
  }

  function summaryValues(sample, history, constrainedSamples) {
    const cpu = sample?.cpu || {};
    const thermal = sample?.thermal || {};
    const power = sample?.power || {};
    const state = deriveSystemState(sample, constrainedSamples);
    const currentClock = number(cpu.average_mhz) === null ? "--" : `${formatNumber(cpu.average_mhz, 0, " MHz")} average`;
    const configuredRange = number(cpu.minimum_mhz) === null || number(cpu.maximum_mhz) === null
      ? "--"
      : `${formatNumber(cpu.minimum_mhz, 0)}–${formatNumber(cpu.maximum_mhz, 0, " MHz")}`;
    const observedClock = number(history?.cpuMinMhz) === null || number(history?.cpuMaxMhz) === null
      ? "--"
      : `${formatNumber(history.cpuMinMhz, 0)}–${formatNumber(history.cpuMaxMhz, 0, " MHz")}`;
    const observedTemp = number(history?.tempMinC) === null || number(history?.tempMaxC) === null
      ? "--"
      : `${formatNumber(history.tempMinC, 1)}–${formatNumber(history.tempMaxC, 1, " °C")}`;
    return {
      "system.state": state.label,
      "cpu.clock": currentClock,
      "cpu.range": configuredRange,
      "cpu.load": number(cpu.load_1m) === null ? "--" : `${formatNumber(cpu.load_1m, 2)} (1 min)`,
      "thermal.sensor": thermal.selected_zone && number(thermal.temperature_c) !== null
        ? `${thermal.selected_zone} ${formatNumber(thermal.temperature_c, 1, " °C")}`
        : "--",
      "thermal.trip": relevantTripText(thermal),
      "thermal.state": thermalLabel(thermal.summary),
      "power.ac": yesNo(power.ac_online),
      "power.battery": batteryText(power),
      "power.state": chargingLabel(power),
      "session.clock": observedClock,
      "session.temp": observedTemp,
      _state: state,
    };
  }

  function detailsSignature(sample = {}) {
    return JSON.stringify({
      cpus: (sample.cpu?.cpus || []).map((entry) => entry.cpu),
      zones: (sample.thermal?.zones || []).map((entry) => [entry.zone, entry.type, (entry.trips || []).map((trip) => `${trip.type}:${trip.temperature_c}`)]),
      cooling: (sample.thermal?.cooling_devices || []).map((entry) => [entry.device, entry.type]),
      supplies: (sample.power?.supplies || []).map((entry) => [entry.name, entry.type]),
      pstate: Object.keys(sample.cpu?.intel_pstate || {}).sort(),
    });
  }

  function detailMetric(label, key) {
    return `<div class="openmmi-runtime-detail-metric"><span>${escapeHtml(label)}</span><strong data-openmmi-runtime-key="${escapeHtml(key)}">--</strong></div>`;
  }

  function detailsTemplate(sample = {}) {
    const cpuRows = (sample.cpu?.cpus || []).map((entry, index) => detailMetric(
      entry.cpu,
      `detail.cpu.${index}`,
    )).join("") || '<p class="openmmi-runtime-empty">CPU frequency data unavailable.</p>';
    const zoneRows = (sample.thermal?.zones || []).map((entry, index) => detailMetric(
      entry.type || entry.zone,
      `detail.zone.${index}`,
    )).join("") || '<p class="openmmi-runtime-empty">Thermal-zone data unavailable.</p>';
    const supplyRows = (sample.power?.supplies || []).map((entry, index) => detailMetric(
      `${entry.name} (${entry.type})`,
      `detail.supply.${index}`,
    )).join("") || '<p class="openmmi-runtime-empty">Power-supply data unavailable.</p>';
    const coolingRows = (sample.thermal?.cooling_devices || []).map((entry, index) => detailMetric(
      entry.type || entry.device,
      `detail.cooling.${index}`,
    )).join("") || '<p class="openmmi-runtime-empty">Cooling-device data unavailable.</p>';
    const pstateRows = Object.keys(sample.cpu?.intel_pstate || {}).sort().map((name) => detailMetric(
      name.replaceAll("_", " "),
      `detail.pstate.${name}`,
    )).join("") || '<p class="openmmi-runtime-empty">Intel pstate data unavailable.</p>';

    return `
      <details><summary>CPU cores</summary><div class="openmmi-runtime-detail-grid">${cpuRows}</div></details>
      <details><summary>Thermal zones</summary><div class="openmmi-runtime-detail-grid">${zoneRows}</div></details>
      <details><summary>Power supplies</summary><div class="openmmi-runtime-detail-grid">${supplyRows}</div></details>
      <details><summary>Cooling devices</summary><div class="openmmi-runtime-detail-grid">${coolingRows}</div></details>
      <details><summary>Intel pstate</summary><div class="openmmi-runtime-detail-grid">${pstateRows}</div></details>
    `;
  }

  function detailValues(sample = {}) {
    const values = {};
    (sample.cpu?.cpus || []).forEach((entry, index) => {
      const governor = entry.governor ? ` · ${entry.governor}` : "";
      const range = number(entry.minimum_mhz) !== null && number(entry.maximum_mhz) !== null
        ? ` (${formatNumber(entry.minimum_mhz, 0)}–${formatNumber(entry.maximum_mhz, 0, " MHz")})`
        : "";
      values[`detail.cpu.${index}`] = `${formatNumber(entry.current_mhz, 0, " MHz")}${range}${governor}`;
    });
    (sample.thermal?.zones || []).forEach((entry, index) => {
      values[`detail.zone.${index}`] = `${formatNumber(entry.temperature_c, 1, " °C")} · ${thermalLabel(entry.state)}`;
    });
    (sample.power?.supplies || []).forEach((entry, index) => {
      const parts = [];
      if (entry.online === true) parts.push("online");
      if (entry.online === false) parts.push("offline");
      if (entry.status) parts.push(entry.status);
      if (number(entry.capacity_percent) !== null) parts.push(`${Math.round(entry.capacity_percent)}%`);
      if (number(entry.reported_power_w) !== null) parts.push(`${formatNumber(entry.reported_power_w, 1, " W")} reported battery-side`);
      values[`detail.supply.${index}`] = parts.join(" · ") || "--";
    });
    (sample.thermal?.cooling_devices || []).forEach((entry, index) => {
      values[`detail.cooling.${index}`] = number(entry.current_state) === null
        ? "--"
        : `${entry.current_state}/${number(entry.maximum_state) === null ? "--" : entry.maximum_state}`;
    });
    Object.entries(sample.cpu?.intel_pstate || {}).forEach(([name, value]) => {
      values[`detail.pstate.${name}`] = String(value);
    });
    return values;
  }


  function frontendActivityValues(windowRef) {
    const connection = windowRef?.openMmiDashboardConnectionController?.snapshot?.() || {};
    const status = windowRef?.openMmiStatusPoller?.getMetrics?.() || {};
    const vehicle = windowRef?.openMmiVehicleRenderer?.getMetrics?.() || {};
    const media = windowRef?.openMmiMediaPerformanceMetrics || {};
    const connectionMetrics = connection.metrics || {};
    return {
      "frontend.connection": connection.state
        ? `${connection.state} · ${connectionMetrics.probes || 0} probes · ${connectionMetrics.recoveries || 0} recoveries`
        : "--",
      "frontend.status": Number.isFinite(Number(status.fetches))
        ? `${status.fetches} fetches · ${status.overlapping_fetches_skipped || 0} overlap skips`
        : "--",
      "frontend.render": Number.isFinite(Number(vehicle.render_calls))
        ? `${vehicle.vehicle_renders || 0} renders · ${vehicle.unchanged_renders_skipped || 0} unchanged skipped`
        : "--",
      "frontend.media": Number.isFinite(Number(media.layout_runs))
        ? `${media.layout_runs} layouts · ${media.layout_requests || 0} requests`
        : "--",
    };
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || windowRef?.document;
    const api = options.api;
    const scheduler = options.scheduler || windowRef || globalThis;
    const intervalMs = Number(options.intervalMs || windowRef?.__openMmiRuntimeDiagnosticsIntervalMs || DEFAULT_INTERVAL_MS);
    let timer = null;
    let inFlight = false;
    let sample = null;
    let history = updateHistory(null, {});
    let constrainedSamples = 0;
    let detailSignature = "";
    let destroyed = false;

    function activeSection() {
      return documentRef?.querySelector?.("[data-openmmi-settings-section].active")?.dataset?.openmmiSettingsSection || "";
    }

    function shouldRun() {
      return !destroyed
        && !documentRef?.hidden
        && activeSection() === "diagnostics"
        && Boolean(documentRef?.querySelector?.("#pageSettings.active"));
    }

    function host() {
      return documentRef?.querySelector?.("#openMmiRuntimeDiagnostics");
    }

    function ensureHost() {
      if (activeSection() !== "diagnostics") return null;
      const panel = documentRef?.querySelector?.("#openmmiSettingsPanel");
      if (!panel) return null;
      let section = host();
      if (section) return section;
      section = documentRef.createElement("section");
      section.id = "openMmiRuntimeDiagnostics";
      section.className = "openmmi-runtime-diagnostics";
      section.setAttribute("aria-label", "Thermal and power diagnostics");
      section.innerHTML = `
        <header><div><span>System runtime</span><h3>Thermal and power</h3></div><strong class="openmmi-runtime-state" data-openmmi-runtime-key="system.state">Loading…</strong></header>
        <div class="openmmi-runtime-summary-grid">
          ${detailMetric("CPU clock", "cpu.clock")}
          ${detailMetric("Configured range", "cpu.range")}
          ${detailMetric("CPU load", "cpu.load")}
          ${detailMetric("Platform sensor", "thermal.sensor")}
          ${detailMetric("Relevant trip", "thermal.trip")}
          ${detailMetric("Thermal state", "thermal.state")}
          ${detailMetric("AC connected", "power.ac")}
          ${detailMetric("Battery", "power.battery")}
          ${detailMetric("Charging state", "power.state")}
          ${detailMetric("Observed clock", "session.clock")}
          ${detailMetric("Observed temperature", "session.temp")}
          ${detailMetric("Dashboard connection", "frontend.connection")}
          ${detailMetric("Status activity", "frontend.status")}
          ${detailMetric("Vehicle renders", "frontend.render")}
          ${detailMetric("Media layouts", "frontend.media")}
        </div>
        <div class="openmmi-runtime-details"></div>
        <p class="openmmi-runtime-note">Reported power values are battery-side driver readings, not charger capacity.</p>
      `;
      const heading = panel.querySelector?.(".openmmi-settings-panel-head");
      if (heading?.after) heading.after(section);
      else if (panel.prepend) panel.prepend(section);
      else panel.appendChild(section);
      return section;
    }

    function setValues(values) {
      const section = ensureHost();
      if (!section) return;
      section.querySelectorAll?.("[data-openmmi-runtime-key]").forEach((node) => {
        const key = node.dataset.openmmiRuntimeKey;
        const next = values[key];
        if (next !== undefined && node.textContent !== String(next)) node.textContent = String(next);
      });
    }

    function applySample(nextSample, countSample = true) {
      sample = nextSample || {};
      if (countSample) {
        const underLoadAtMinimum = Boolean(sample.cpu?.near_minimum && sample.cpu?.load_high);
        constrainedSamples = underLoadAtMinimum ? constrainedSamples + 1 : 0;
        history = updateHistory(history, sample);
      }
      const values = summaryValues(sample, history, constrainedSamples);
      const section = ensureHost();
      if (!section) return;
      section.dataset.state = values._state.level;
      setValues(Object.assign({}, values, frontendActivityValues(windowRef), detailValues(sample)));
      const signature = detailsSignature(sample);
      const detailHost = section.querySelector?.(".openmmi-runtime-details");
      if (detailHost && signature !== detailSignature) {
        const openStates = Array.from(detailHost.querySelectorAll?.("details") || []).map((node) => node.open);
        detailHost.innerHTML = detailsTemplate(sample);
        Array.from(detailHost.querySelectorAll?.("details") || []).forEach((node, index) => {
          if (index < openStates.length) node.open = openStates[index];
        });
        detailSignature = signature;
        setValues(Object.assign({}, values, frontendActivityValues(windowRef), detailValues(sample)));
      }
      windowRef?.dispatchEvent?.(new windowRef.CustomEvent("openmmi:runtimediagnostics", { detail: { sample, state: values._state } }));
    }

    function applyError() {
      const section = ensureHost();
      if (!section) return;
      section.dataset.state = "neutral";
      setValues({
        "system.state": "Unavailable",
        "cpu.clock": "--",
        "cpu.range": "--",
        "cpu.load": "--",
        "thermal.sensor": "--",
        "thermal.trip": "--",
        "thermal.state": "Unavailable",
        "power.ac": "--",
        "power.battery": "--",
        "power.state": "Unknown",
        ...frontendActivityValues(windowRef),
      });
    }

    function clearTimer() {
      if (timer !== null) scheduler.clearTimeout(timer);
      timer = null;
    }

    function schedule() {
      clearTimer();
      if (!shouldRun()) return;
      timer = scheduler.setTimeout(poll, Math.max(100, intervalMs));
    }

    async function poll() {
      clearTimer();
      if (!shouldRun() || inFlight || !api?.getJson) return;
      inFlight = true;
      try {
        applySample(await api.getJson(ENDPOINT));
      } catch (_) {
        applyError();
      } finally {
        inFlight = false;
        schedule();
      }
    }

    function sync() {
      if (!shouldRun()) {
        clearTimer();
        return;
      }
      const section = ensureHost();
      if (sample && section) applySample(sample, false);
      if (timer === null && !inFlight) poll();
    }

    function install() {
      windowRef?.addEventListener?.("openmmi:settingsrender", sync);
      windowRef?.addEventListener?.("openmmi:pagechange", sync);
      documentRef?.addEventListener?.("visibilitychange", sync);
      documentRef?.addEventListener?.("DOMContentLoaded", sync);
      windowRef?.requestAnimationFrame?.(sync);
      return controller;
    }

    function destroy() {
      destroyed = true;
      clearTimer();
      windowRef?.removeEventListener?.("openmmi:settingsrender", sync);
      windowRef?.removeEventListener?.("openmmi:pagechange", sync);
      documentRef?.removeEventListener?.("visibilitychange", sync);
      documentRef?.removeEventListener?.("DOMContentLoaded", sync);
    }

    const controller = {
      install,
      destroy,
      poll,
      sync,
      applySample,
      snapshot() {
        return { sample, history: Object.assign({}, history), constrainedSamples, running: timer !== null || inFlight };
      },
    };
    return controller;
  }

  function install(options = {}) {
    return createController(options).install();
  }

  return {
    ENDPOINT,
    DEFAULT_INTERVAL_MS,
    REQUIRED_CONSTRAINED_SAMPLES,
    escapeHtml,
    chargingLabel,
    thermalLabel,
    deriveSystemState,
    updateHistory,
    summaryValues,
    detailsSignature,
    frontendActivityValues,
    createController,
    install,
  };
});
