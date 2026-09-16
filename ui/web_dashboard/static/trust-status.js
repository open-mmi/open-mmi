(function openMmiTrustStatusModule(root, factory) {
  const moduleApi = factory(root);
  if (typeof module === "object" && module.exports) module.exports = moduleApi;
  if (root) root.openMmiTrustStatus = moduleApi;
})(typeof globalThis !== "undefined" ? globalThis : this, function createTrustStatusModule(root) {
  "use strict";

  const ENDPOINT = "/api/trust/status";
  const VALID_STATUSES = new Set(["PASS", "FAIL", "UNVERIFIED"]);

  function normalizeStatus(value) {
    const status = String(value || "").trim().toUpperCase();
    return VALID_STATUSES.has(status) ? status : "UNVERIFIED";
  }

  function escapeHtml(value) {
    return String(value ?? "--")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isObject(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
  }

  function checkById(checks, id) {
    return checks.find((check) => isObject(check) && check.id === id) || null;
  }

  function buildModel(payload = {}) {
    const report = isObject(payload.report) ? payload.report : null;
    const manifest = report && isObject(report.manifest) ? report.manifest : {};
    const rawCapabilities = isObject(manifest.capabilities) ? manifest.capabilities : {};
    const checks = report && Array.isArray(report.checks) ? report.checks : [];

    const capabilities = Object.keys(rawCapabilities)
      .sort()
      .map((id) => {
        const capability = isObject(rawCapabilities[id]) ? rawCapabilities[id] : {};
        return {
          id,
          policy: String(capability.policy || "--"),
          assurance: String(capability.assurance || "--"),
          purposes: Array.isArray(capability.purposes)
            ? capability.purposes.map((value) => String(value))
            : [],
        };
      });

    const acceptedCheck = checkById(checks, "owner.accepted-release-state");
    const acceptedEvidence = acceptedCheck && isObject(acceptedCheck.evidence)
      ? acceptedCheck.evidence
      : {};

    const telemetry = report && isObject(report.telemetry_authorization)
      ? report.telemetry_authorization
      : {};

    return {
      status: normalizeStatus(payload.status),
      error: payload.error ? String(payload.error) : null,

      manifest: {
        available: manifest.available === true,
        generation: manifest.policy_generation ?? null,
        digest: manifest.digest ? String(manifest.digest) : null,
        capabilities,
      },

      ownerTrust: {
        status: acceptedCheck ? normalizeStatus(acceptedCheck.status) : "UNVERIFIED",
        established: acceptedEvidence.established === true
          ? true
          : acceptedEvidence.established === false
            ? false
            : null,
        generation: acceptedEvidence.accepted_generation ?? null,
        manifestDigest: acceptedEvidence.accepted_manifest_digest
          ? String(acceptedEvidence.accepted_manifest_digest)
          : null,
        currentRelation: acceptedEvidence.current_relation
          ? String(acceptedEvidence.current_relation)
          : null,
      },

      telemetry: {
        authorized: telemetry.authorized === true
          ? true
          : telemetry.authorized === false
            ? false
            : null,
        state: telemetry.state ? String(telemetry.state) : null,
        scopeDigest: telemetry.scope_digest ? String(telemetry.scope_digest) : null,
        purpose: isObject(telemetry.scope) && telemetry.scope.purpose
          ? String(telemetry.scope.purpose)
          : null,
      },

      checks: checks
        .filter(isObject)
        .map((check) => {
          const evidence = isObject(check.evidence) ? check.evidence : {};
          const rawDimensions = isObject(evidence.evidence_dimensions)
            ? evidence.evidence_dimensions
            : null;
          const evidenceDimensions = rawDimensions
            ? {
                declaredPolicy: normalizeStatus(rawDimensions["declared-policy"]),
                staticContract: normalizeStatus(rawDimensions["static-contract"]),
                runtimeEnforcement: normalizeStatus(rawDimensions["runtime-enforcement"]),
                hardwareQualification: normalizeStatus(rawDimensions["hardware-qualification"]),
              }
            : null;
          return {
            id: String(check.id || "unknown"),
            status: normalizeStatus(check.status),
            summary: String(check.summary || "No explanation available."),
            evidence,
            evidenceScopes: Array.isArray(evidence.evidence_scopes)
              ? evidence.evidence_scopes.map((value) => String(value))
              : evidence.evidence_scope
                ? [String(evidence.evidence_scope)]
                : [],
            liveRuntimeObservation: typeof evidence.live_runtime_observation === "boolean"
              ? evidence.live_runtime_observation
              : null,
            hardwareObservation: typeof evidence.hardware_observation === "boolean"
              ? evidence.hardware_observation
              : null,
            evidenceDimensions,
          };
        }),
    };
  }

  function metric(label, value) {
    return `
      <div class="openmmi-settings-metric">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `;
  }

  function row(title, note, value) {
    return `
      <div class="openmmi-setting-row">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <small>${escapeHtml(note)}</small>
        </div>
        <div class="openmmi-setting-controls">
          <strong>${escapeHtml(value)}</strong>
        </div>
      </div>
    `;
  }

  function ownerTrustText(ownerTrust) {
    if (ownerTrust.established === true) return "ESTABLISHED";
    if (ownerTrust.established === false) return "NOT ESTABLISHED";
    return ownerTrust.status;
  }

  function telemetryText(telemetry) {
    if (telemetry.authorized === true) return "AUTHORIZED";
    if (telemetry.authorized === false) return "NOT AUTHORIZED";
    return String(telemetry.state || "UNVERIFIED").toUpperCase();
  }

  function capabilitiesTemplate(capabilities) {
    if (!capabilities.length) {
      return row(
        "Capabilities",
        "No valid local Trust Manifest capability evidence is available.",
        "UNVERIFIED",
      );
    }

    return capabilities.map((capability) => {
      const purposes = capability.purposes.length
        ? ` Purposes: ${capability.purposes.join(", ")}.`
        : "";

      return row(
        capability.id,
        `Declared policy: ${capability.policy}.${purposes}`,
        `declared assurance: ${capability.assurance}`,
      );
    }).join("");
  }

  function checksTemplate(checks) {
    if (!checks.length) {
      return row(
        "Trust checks",
        "No local Trust Inspector checks are available.",
        "UNVERIFIED",
      );
    }

    return checks.map((check) => {
      const scope = check.evidenceScopes.length
        ? check.evidenceScopes.map((value) => String(value).replace(/-/g, " ")).join(" + ")
        : "evidence scope unspecified";
      const runtime = check.liveRuntimeObservation === true
        ? "live runtime observed"
        : check.liveRuntimeObservation === false
          ? "no live runtime observation"
          : "runtime observation unspecified";
      const hardware = check.hardwareObservation === true
        ? "hardware observed"
        : check.hardwareObservation === false
          ? "no hardware observation"
          : "hardware observation unspecified";
      const dimensions = check.evidenceDimensions
        ? ` Dimensions: declared policy ${check.evidenceDimensions.declaredPolicy}`
          + ` · static contract ${check.evidenceDimensions.staticContract}`
          + ` · runtime enforcement ${check.evidenceDimensions.runtimeEnforcement}`
          + ` · hardware qualification ${check.evidenceDimensions.hardwareQualification}.`
        : "";

      return `
        <div class="openmmi-setting-row" data-openmmi-trust-check="${escapeHtml(check.id)}">
          <div>
            <strong>${escapeHtml(check.id)}</strong>
            <small>${escapeHtml(check.summary)} Evidence: ${escapeHtml(scope)} · ${escapeHtml(runtime)} · ${escapeHtml(hardware)}.${escapeHtml(dimensions)}</small>
          </div>
          <div class="openmmi-setting-controls">
            <strong>${escapeHtml(check.status)}</strong>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderPayload(payload = {}) {
    const model = buildModel(payload);

    const error = model.error
      ? row(
          "Evidence unavailable",
          model.error,
          "UNVERIFIED",
        )
      : "";

    const manifestGeneration = model.manifest.available
      ? String(model.manifest.generation ?? "--")
      : "UNVERIFIED";

    const manifestDigest = model.manifest.available && model.manifest.digest
      ? model.manifest.digest
      : "--";

    const ownerDetails = [
      model.ownerTrust.generation !== null
        ? `Generation ${model.ownerTrust.generation}`
        : null,
      model.ownerTrust.currentRelation
        ? `relation ${model.ownerTrust.currentRelation}`
        : null,
    ].filter(Boolean).join(" · ") || "Accepted owner boundary evidence.";

    const telemetryDetails = [
      model.telemetry.purpose
        ? `Purpose: ${model.telemetry.purpose}`
        : null,
      model.telemetry.scopeDigest
        ? `Scope: ${model.telemetry.scopeDigest}`
        : null,
    ].filter(Boolean).join(" · ") || "Local telemetry authorization state.";

    return `
      <div class="openmmi-settings-panel-head">
        <span>Trust</span>
        <small>read-only local evidence</small>
      </div>

      ${error}

      ${metric("Overall", model.status)}

      <div class="openmmi-settings-subhead">
        <span>Trust Manifest</span>
        <small>declared policy and assurance</small>
      </div>

      ${metric("Policy generation", manifestGeneration)}
      ${metric("Manifest digest", manifestDigest)}
      ${capabilitiesTemplate(model.manifest.capabilities)}

      <div class="openmmi-settings-subhead">
        <span>Owner trust</span>
        <small>accepted local boundary</small>
      </div>

      ${row(
        "Accepted owner trust",
        ownerDetails,
        ownerTrustText(model.ownerTrust),
      )}

      <div class="openmmi-settings-subhead">
        <span>Privacy</span>
        <small>local authorization</small>
      </div>

      ${row(
        "Telemetry",
        telemetryDetails,
        telemetryText(model.telemetry),
      )}

      <details class="openmmi-settings-diagnostics-details">
        <summary>Trust evidence checks (${model.checks.length})</summary>
        <div class="openmmi-settings-diagnostics-values">
          ${checksTemplate(model.checks)}
        </div>
      </details>
    `;
  }

  function createController(options = {}) {
    const api = options.api;
    const documentRef = options.document || (root && root.document);
    const windowRef = options.window || root;
    let requestSerial = 0;

    function host() {
      return documentRef?.querySelector?.("[data-openmmi-trust-panel]") || null;
    }

    async function refresh() {
      const initialHost = host();
      if (!initialHost) return null;

      const serial = ++requestSerial;

      initialHost.innerHTML = renderPayload({
        status: "UNVERIFIED",
        report: null,
        error: "Loading fresh local trust evidence.",
      });

      let payload;
      try {
        payload = await api.getJson(ENDPOINT);
      } catch (_) {
        payload = {
          status: "UNVERIFIED",
          report: null,
          error: "Trust inspection evidence is unavailable.",
        };
      }

      if (serial !== requestSerial) return payload;

      const currentHost = host();
      if (currentHost) currentHost.innerHTML = renderPayload(payload);
      return payload;
    }

    function scheduleRefresh() {
      if (host()) void refresh();
    }

    function install() {
      if (!api || typeof api.getJson !== "function") {
        throw new TypeError("Trust status requires the dashboard GET API");
      }

      windowRef?.addEventListener?.("openmmi:settingsrender", scheduleRefresh);
      windowRef?.addEventListener?.("openmmi:pagechange", scheduleRefresh);
      scheduleRefresh();

      return controller;
    }

    const controller = Object.freeze({
      refresh,
      install,
    });

    return controller;
  }

  function install(options = {}) {
    return createController(options).install();
  }

  return Object.freeze({
    ENDPOINT,
    buildModel,
    createController,
    escapeHtml,
    install,
    normalizeStatus,
    renderPayload,
  });
});
