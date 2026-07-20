(function openMmiVehicleSetupSettingsModule(root, factory) {
  const moduleApi = factory(root);
  if (typeof module === "object" && module.exports) module.exports = moduleApi;
  if (root) root.openMmiVehicleSetupSettings = moduleApi;
})(typeof globalThis !== "undefined" ? globalThis : this, function createVehicleSetupSettingsModule(root) {
  "use strict";

  const ENDPOINT = "/api/system/vehicle-setup";
  const PREVIEW_ENDPOINT = "/api/system/vehicle-setup/preview";
  const SOURCES = Object.freeze(["maintained", "custom"]);
  const IDENTIFIER_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
  const INTERFACE_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$/;

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function identityKey(identity = {}) {
    const source = String(identity.source || "");
    const identifier = String(identity.id || "");
    return source && IDENTIFIER_RE.test(identifier) ? `${source}:${identifier}` : "";
  }

  function identityFromKey(key) {
    const separator = String(key || "").indexOf(":");
    if (separator < 1) return null;
    const source = String(key).slice(0, separator);
    const identifier = String(key).slice(separator + 1);
    if (!SOURCES.includes(source) || !IDENTIFIER_RE.test(identifier)) return null;
    return { source, id: identifier };
  }

  function sourceLabel(source) {
    if (source === "maintained") return "Maintained";
    if (source === "custom") return "Custom";
    if (source === "external") return "External";
    return "Unavailable";
  }

  function bitrateLabel(value) {
    const bitrate = Number(value);
    if (!Number.isFinite(bitrate) || bitrate <= 0) return "not declared";
    if (bitrate % 1000 === 0) return `${bitrate / 1000} kbit/s`;
    return `${bitrate} bit/s`;
  }

  function entryFor(entries, key) {
    return (Array.isArray(entries) ? entries : []).find((entry) => identityKey(entry) === key) || null;
  }

  function optionGroups(entries, selectedKey, fallbackIdentity = {}) {
    const catalogue = Array.isArray(entries) ? entries : [];
    const groups = SOURCES.map((source) => {
      const options = catalogue
        .filter((entry) => entry?.source === source)
        .map((entry) => {
          const key = identityKey(entry);
          const selected = key === selectedKey ? " selected" : "";
          const disabled = entry?.valid === false ? " disabled" : "";
          const suffix = entry?.valid === false ? " — invalid" : "";
          return `<option value="${escapeHtml(key)}"${selected}${disabled}>${escapeHtml(entry?.display_name || entry?.id || "Unnamed")}${escapeHtml(suffix)}</option>`;
        })
        .join("");
      return options ? `<optgroup label="${sourceLabel(source)}">${options}</optgroup>` : "";
    }).join("");

    if (selectedKey && !entryFor(catalogue, selectedKey)) {
      const label = fallbackIdentity?.id || "Unavailable selection";
      return `<optgroup label="Unavailable"><option value="${escapeHtml(selectedKey)}" selected disabled>${escapeHtml(label)}</option></optgroup>${groups}`;
    }
    return groups;
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || windowRef?.document;
    const api = options.api || windowRef?.openMmiApi;
    if (!windowRef || !documentRef || !api) {
      throw new Error("Vehicle setup settings require window, document and API client");
    }

    let snapshot = null;
    let draft = null;
    let draftDirty = false;
    let loading = false;
    let attempted = false;
    let connectionUnavailable = false;
    let errorMessage = "";
    let preview = null;
    let previewLoading = false;
    let previewError = "";
    let previewGeneration = 0;

    function activeSection() {
      return documentRef.querySelector("[data-openmmi-settings-section].active")
        ?.dataset?.openmmiSettingsSection || "";
    }

    function activeIdentity(kind) {
      return snapshot?.active?.[kind] || {};
    }

    function seedDraft() {
      draft = {
        vehicle: identityKey(activeIdentity("vehicle")),
        bindings: identityKey(activeIdentity("bindings")),
      };
      draftDirty = false;
    }

    function catalogue(kind) {
      return snapshot?.catalogue?.[kind === "vehicle" ? "profiles" : "bindings"] || [];
    }

    function selectedEntry(kind) {
      return entryFor(catalogue(kind), draft?.[kind] || "");
    }

    function identityDisplay(kind, identity) {
      return entryFor(catalogue(kind), identityKey(identity))?.display_name
        || identity?.id
        || "--";
    }

    function draftDiffers() {
      if (!draft || !snapshot) return false;
      return draft.vehicle !== identityKey(activeIdentity("vehicle"))
        || draft.bindings !== identityKey(activeIdentity("bindings"));
    }

    function clearPreview() {
      previewGeneration += 1;
      preview = null;
      previewLoading = false;
      previewError = "";
    }

    function setDraft(kind, key) {
      if (!SOURCES.some((source) => String(key).startsWith(`${source}:`))) return false;
      const entry = entryFor(catalogue(kind), key);
      if (!entry || entry.valid === false) return false;
      if (!draft) seedDraft();
      draft[kind] = key;
      draftDirty = draftDiffers();
      clearPreview();
      render();
      return true;
    }

    function validationNote(entry, fallback) {
      if (!entry) return fallback;
      const errors = entry.validation?.errors?.length || 0;
      const warnings = entry.validation?.warnings?.length || 0;
      if (errors) return `${errors} validation error${errors === 1 ? "" : "s"}`;
      if (warnings) return `${warnings} catalogue warning${warnings === 1 ? "" : "s"}`;
      return `${sourceLabel(entry.source)} catalogue · valid`;
    }

    function selectedBus() {
      const profile = selectedEntry("vehicle");
      const name = profile?.default_bus || snapshot?.active?.active_bus || "";
      const bus = (profile?.buses || []).find((entry) => entry?.name === name)
        || profile?.buses?.[0]
        || {};
      return { name, ...bus };
    }

    function previewRequest() {
      if (!draft || !snapshot) return null;
      const vehicle = identityFromKey(draft.vehicle);
      const bindings = identityFromKey(draft.bindings);
      const bus = selectedBus();
      const busName = String(bus.name || "");
      const interfaceName = String(bus.interface || snapshot.active?.interface || "");
      if (!vehicle || !bindings || !IDENTIFIER_RE.test(busName) || !INTERFACE_RE.test(interfaceName)) {
        return null;
      }
      return {
        vehicle,
        bindings,
        runtime: {
          active_bus: busName,
          buses: { [busName]: { interface: interfaceName } },
        },
      };
    }

    function compatibilityLabel() {
      const report = snapshot?.compatibility || {};
      const matched = report.emitted_and_bound?.length || 0;
      const emittedMissing = report.emitted_unbound?.length || 0;
      const unused = report.bound_unemitted?.length || 0;
      if (emittedMissing) return `${matched} matched · ${emittedMissing} unbound event${emittedMissing === 1 ? "" : "s"}`;
      if (unused) return `${matched} matched · ${unused} unused binding${unused === 1 ? "" : "s"}`;
      return `${matched} events matched`;
    }

    function changeValue(field, value) {
      if (value === null || value === undefined || value === "") return "Not configured";
      if (field === "vehicle" || field === "bindings") {
        const kind = field === "vehicle" ? "vehicle" : "bindings";
        return `${identityDisplay(kind, value)} · ${sourceLabel(value?.source)}`;
      }
      return String(value);
    }

    function changeLabel(field) {
      return ({
        vehicle: "Vehicle profile",
        bindings: "Bindings",
        active_bus: "Active CAN bus",
        interface: "CAN adapter",
      })[field] || String(field || "Configuration");
    }

    function previewEffects(effects = {}) {
      const labels = [
        ["write_canonical_configuration", "Save the reviewed vehicle setup"],
        ["write_systemd_runtime", "Update the CAN service configuration"],
        ["write_udev_rules", "Update CAN adapter provisioning"],
        ["reload_user_manager", "Reload the user service manager"],
        ["reload_udev", "Reload CAN adapter rules"],
        ["restart_can_service", "Restart the CAN service"],
      ];
      return labels.filter(([key]) => effects?.[key] === true).map(([, label]) => label);
    }

    function previewTemplate() {
      if (previewLoading) {
        return `<div class="openmmi-config-message warning" role="status" data-testid="vehicle-setup-preview-loading">Checking the selected setup…</div>`;
      }
      if (previewError) {
        return `<div class="openmmi-config-message error" role="status" data-testid="vehicle-setup-preview-error">${escapeHtml(previewError)}</div>`;
      }
      if (!preview) return "";

      const changes = Array.isArray(preview.plan?.changes) ? preview.plan.changes : [];
      const warnings = Array.isArray(preview.validation?.warnings) ? preview.validation.warnings : [];
      const effects = previewEffects(preview.plan?.effects);
      const interfaceState = preview.interface || {};
      const interfaceText = interfaceState.name
        ? `${interfaceState.name}${interfaceState.present === true ? interfaceState.up === true ? " · present and up" : " · present but down" : " · not detected"}`
        : "CAN adapter unavailable";
      const changeRows = changes.length
        ? changes.map((change) => `
            <div class="openmmi-vehicle-preview-change">
              <span>${escapeHtml(changeLabel(change?.field))}</span>
              <strong><span>${escapeHtml(changeValue(change?.field, change?.from))}</span><b aria-hidden="true">→</b><span>${escapeHtml(changeValue(change?.field, change?.to))}</span></strong>
            </div>
          `).join("")
        : `<p class="openmmi-vehicle-preview-empty">No active configuration values would change.</p>`;
      const warningRows = warnings.length
        ? `<ul class="openmmi-vehicle-preview-warnings">${warnings.map((warning) => `<li>${escapeHtml(warning?.message || warning?.code || "Configuration warning")}</li>`).join("")}</ul>`
        : `<p class="openmmi-vehicle-preview-ok">No compatibility warnings were reported.</p>`;
      const effectRows = effects.length
        ? `<ul>${effects.map((effect) => `<li>${escapeHtml(effect)}</li>`).join("")}</ul>`
        : `<p>No service or adapter changes are required.</p>`;

      return `
        <section class="openmmi-vehicle-setup-preview" aria-label="Vehicle setup review" data-testid="vehicle-setup-preview">
          <div class="openmmi-settings-subhead"><span>Review changes</span><small>read-only preview</small></div>
          <div class="openmmi-vehicle-preview-changes">${changeRows}</div>
          <div class="openmmi-settings-metric openmmi-vehicle-preview-interface"><span>Selected CAN adapter</span><strong data-testid="vehicle-setup-preview-interface">${escapeHtml(interfaceText)}</strong></div>
          <div class="openmmi-vehicle-preview-block">
            <strong>Compatibility</strong>
            ${warningRows}
          </div>
          <details class="openmmi-vehicle-preview-effects" data-testid="vehicle-setup-preview-effects">
            <summary>What applying this setup would do</summary>
            ${effectRows}
          </details>
          <div class="openmmi-config-message warning" role="status">Preview only — applying vehicle setup is unavailable in this build.</div>
          <div class="openmmi-config-actions openmmi-vehicle-setup-actions">
            <button type="button" class="openmmi-settings-link" data-openmmi-vehicle-setup-preview-close="true" data-testid="vehicle-setup-preview-close">Back to selection</button>
            <button type="button" class="openmmi-setting-pill" data-testid="vehicle-setup-apply" disabled>Apply setup</button>
          </div>
        </section>
      `;
    }

    async function reviewDraft() {
      const request = previewRequest();
      if (!request) {
        previewError = "Choose a valid setup before requesting a review";
        render();
        return null;
      }
      const generation = ++previewGeneration;
      preview = null;
      previewError = "";
      previewLoading = true;
      render();
      try {
        const result = await api.postJson(PREVIEW_ENDPOINT, request, { usePayloadError: true });
        if (generation !== previewGeneration) return null;
        if (result?.read_only !== true || result?.apply_available !== false || result?.state !== "ready") {
          throw new Error("Vehicle setup preview was not safely available");
        }
        preview = result;
        return preview;
      } catch (error) {
        if (generation === previewGeneration) {
          previewError = error?.message || "Could not preview vehicle setup";
        }
        throw error;
      } finally {
        if (generation === previewGeneration) {
          previewLoading = false;
          render();
        }
      }
    }

    function template() {
      if (!snapshot) {
        const message = errorMessage || (loading ? "Loading vehicle catalogue…" : "Vehicle setup has not been loaded");
        const kind = errorMessage ? "error" : "warning";
        return `
          <div class="openmmi-vehicle-setup-panel" data-openmmi-vehicle-setup-panel="true">
            <div class="openmmi-settings-panel-head"><span>Vehicle setup</span><small>single CAN input</small></div>
            <div class="openmmi-config-message ${kind}" role="status">${escapeHtml(message)}</div>
            <button type="button" class="openmmi-settings-link" data-openmmi-vehicle-setup-refresh="true" data-testid="vehicle-setup-refresh" ${loading ? "disabled" : ""}>Retry</button>
          </div>
        `;
      }

      if (!draft) seedDraft();
      const active = snapshot.active || {};
      const activeVehicle = activeIdentity("vehicle");
      const activeBindings = activeIdentity("bindings");
      const profile = selectedEntry("vehicle");
      const bindings = selectedEntry("bindings");
      const bus = selectedBus();
      const changed = draftDiffers();
      const canReview = Boolean(previewRequest()) && !loading && !previewLoading;
      const activeReady = active.state === "ready";
      const statusText = preview
        ? changed
          ? "Review ready — changes remain unapplied."
          : "Review ready — the current setup would remain unchanged."
        : changed
          ? "Changes not applied — selections are a local draft only."
        : activeReady
          ? "Current active setup is ready."
          : `Active setup needs attention: ${(active.errors || []).join(", ") || "status unavailable"}`;
      const statusKind = changed ? "warning" : activeReady ? "success" : "error";
      const interfaceName = bus.interface || active.interface || "";
      const interfaceEntry = (snapshot.interfaces || []).find((entry) => entry?.name === interfaceName);
      const interfacePresent = interfaceEntry?.present === true
        || (interfaceName === active.interface && active.interface_present === true);
      const interfaceText = interfaceName
        ? `${interfaceName}${interfacePresent ? " · connected" : " · not detected"}`
        : "not selected";
      const issues = snapshot.catalogue?.issues || [];
      const issueText = issues.length
        ? `${issues.length} catalogue issue${issues.length === 1 ? "" : "s"}`
        : "catalogue ready";

      return `
        <div class="openmmi-vehicle-setup-panel" data-openmmi-vehicle-setup-panel="true" data-openmmi-vehicle-setup-ready="true">
          <div class="openmmi-settings-panel-head"><span>Vehicle setup</span><small>${escapeHtml(snapshot.runtime_mode === "single" ? "single CAN input" : snapshot.runtime_mode || "runtime")}</small></div>
          <div class="openmmi-config-message ${statusKind}" role="status" data-testid="vehicle-setup-status">${escapeHtml(statusText)}</div>

          <div class="openmmi-vehicle-setup-active" aria-label="Active vehicle setup">
            <div class="openmmi-settings-metric"><span>Active profile</span><strong data-testid="vehicle-setup-active-profile">${escapeHtml(identityDisplay("vehicle", activeVehicle))} · ${sourceLabel(activeVehicle.source)}</strong></div>
            <div class="openmmi-settings-metric"><span>Active bindings</span><strong data-testid="vehicle-setup-active-bindings">${escapeHtml(identityDisplay("bindings", activeBindings))} · ${sourceLabel(activeBindings.source)}</strong></div>
          </div>

          <div class="openmmi-settings-subhead"><span>Draft selection</span><small>not applied</small></div>
          <div class="openmmi-vehicle-setup-selectors">
            <label>
              <span><strong>Vehicle profile</strong><small>${escapeHtml(validationNote(profile, "Choose a valid profile"))}</small></span>
              <select data-openmmi-vehicle-setup-select="vehicle" data-testid="vehicle-setup-profile" ${loading || previewLoading ? "disabled" : ""}>
                ${optionGroups(catalogue("vehicle"), draft.vehicle, activeVehicle)}
              </select>
            </label>
            <label>
              <span><strong>Bindings</strong><small>${escapeHtml(validationNote(bindings, "Choose valid bindings"))}</small></span>
              <select data-openmmi-vehicle-setup-select="bindings" data-testid="vehicle-setup-bindings" ${loading || previewLoading ? "disabled" : ""}>
                ${optionGroups(catalogue("bindings"), draft.bindings, activeBindings)}
              </select>
            </label>
          </div>

          <div class="openmmi-settings-subhead"><span>CAN input</span><small>profile summary</small></div>
          <div class="openmmi-vehicle-setup-summary">
            <div class="openmmi-settings-metric"><span>Active CAN bus</span><strong data-testid="vehicle-setup-bus">${escapeHtml(bus.name || active.active_bus || "--")}</strong></div>
            <div class="openmmi-settings-metric"><span>CAN adapter</span><strong data-testid="vehicle-setup-interface">${escapeHtml(interfaceText)}</strong></div>
            <div class="openmmi-settings-metric"><span>Expected bitrate</span><strong data-testid="vehicle-setup-bitrate">${escapeHtml(bitrateLabel(bus.bitrate))}</strong></div>
            <div class="openmmi-settings-metric"><span>Active compatibility</span><strong data-testid="vehicle-setup-compatibility">${escapeHtml(compatibilityLabel())}</strong></div>
          </div>

          <div class="openmmi-config-actions openmmi-vehicle-setup-actions">
            <button type="button" class="openmmi-settings-link" data-openmmi-vehicle-setup-refresh="true" data-testid="vehicle-setup-refresh" ${loading || previewLoading ? "disabled" : ""}>Refresh status</button>
            <button type="button" class="openmmi-setting-pill" data-openmmi-vehicle-setup-review="true" data-testid="vehicle-setup-review" ${canReview ? "" : "disabled"}>${previewLoading ? "Checking setup…" : preview ? "Refresh review" : changed ? "Review changes" : "Review current setup"}</button>
          </div>
          <p class="openmmi-vehicle-setup-note">Review is read-only. Activation remains unavailable until the privileged apply boundary is implemented and qualified.</p>

          ${previewTemplate()}

          <details class="openmmi-vehicle-setup-technical" data-testid="vehicle-setup-technical">
            <summary>Technical details</summary>
            <div class="openmmi-settings-metric"><span>Active state</span><strong>${escapeHtml(active.state || "unavailable")}</strong></div>
            <div class="openmmi-settings-metric"><span>Catalogue</span><strong>${escapeHtml(issueText)}</strong></div>
            <div class="openmmi-settings-metric"><span>Profile revision</span><strong>${escapeHtml(activeVehicle.revision || "--")}</strong></div>
            <div class="openmmi-settings-metric"><span>Bindings revision</span><strong>${escapeHtml(activeBindings.revision || "--")}</strong></div>
          </details>
        </div>
      `;
    }

    function render() {
      if (activeSection() !== "vehicle-setup") return false;
      const panel = documentRef.querySelector("#openmmiSettingsPanel");
      if (!panel) return false;
      panel.innerHTML = template();
      return true;
    }

    async function refresh() {
      clearPreview();
      loading = true;
      attempted = true;
      errorMessage = "";
      render();
      try {
        const next = await api.getJson(ENDPOINT, { usePayloadError: true });
        snapshot = next;
        if (!draft || !draftDirty) seedDraft();
        return snapshot;
      } catch (error) {
        errorMessage = error?.message || "Could not load vehicle setup";
        connectionUnavailable = true;
        throw error;
      } finally {
        loading = false;
        render();
      }
    }

    function renderActive() {
      if (activeSection() !== "vehicle-setup") return;
      render();
      if (!attempted && !loading) refresh().catch(() => {});
    }

    function changeHandler(event) {
      const select = event.target?.closest?.("[data-openmmi-vehicle-setup-select]");
      if (!select) return;
      setDraft(select.dataset.openmmiVehicleSetupSelect, select.value);
    }

    function clickHandler(event) {
      const refreshButton = event.target?.closest?.("[data-openmmi-vehicle-setup-refresh]");
      if (refreshButton) {
        refresh().catch(() => {});
        return;
      }
      const reviewButton = event.target?.closest?.("[data-openmmi-vehicle-setup-review]");
      if (reviewButton && !reviewButton.disabled) {
        reviewDraft().catch(() => {});
        return;
      }
      const closeButton = event.target?.closest?.("[data-openmmi-vehicle-setup-preview-close]");
      if (closeButton) {
        clearPreview();
        render();
      }
    }

    documentRef.addEventListener("change", changeHandler);
    documentRef.addEventListener("click", clickHandler);
    windowRef.addEventListener("openmmi:settingsrender", () => windowRef.requestAnimationFrame(renderActive));
    windowRef.addEventListener("openmmi:dashboardconnection", (event) => {
      if (event?.detail?.state !== "ready") {
        if (attempted) connectionUnavailable = true;
        return;
      }
      if (connectionUnavailable && attempted && !loading && activeSection() === "vehicle-setup") {
        connectionUnavailable = false;
        refresh().catch(() => {});
      }
    });

    return Object.freeze({
      activeSection,
      draftDiffers,
      previewRequest,
      refresh,
      render,
      renderActive,
      reviewDraft,
      setDraft,
      snapshot: () => snapshot,
      draft: () => draft ? { ...draft } : null,
      preview: () => preview,
      template,
    });
  }

  function install(options = {}) {
    return createController(options);
  }

  return Object.freeze({
    ENDPOINT,
    PREVIEW_ENDPOINT,
    createController,
    escapeHtml,
    identityFromKey,
    identityKey,
    install,
  });
});
