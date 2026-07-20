(function openMmiVehicleSetupSettingsModule(root, factory) {
  const moduleApi = factory(root);
  if (typeof module === "object" && module.exports) module.exports = moduleApi;
  if (root) root.openMmiVehicleSetupSettings = moduleApi;
})(typeof globalThis !== "undefined" ? globalThis : this, function createVehicleSetupSettingsModule(root) {
  "use strict";

  const ENDPOINT = "/api/system/vehicle-setup";
  const PREVIEW_ENDPOINT = "/api/system/vehicle-setup/preview";
  const APPLY_ENDPOINT = "/api/system/vehicle-setup/apply";
  const COPY_ENDPOINT = "/api/system/vehicle-custom/create";
  const COORDINATOR_ENDPOINT = "/api/system/vehicle-setup/coordinator";
  const ACTIVE_APPLY_STATES = new Set(["validating", "applying", "reloading", "verifying", "restoring"]);
  const TERMINAL_APPLY_STATES = new Set(["idle", "complete", "failed"]);
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
    let coordinator = null;
    let coordinatorError = "";
    let applyBusy = false;
    let applyMessage = "";
    let applyMessageKind = "";
    let applyState = null;
    let applyPollTimer = null;
    let applyPollDeadline = 0;
    let copyBusyKind = "";
    let copyMessage = "";
    let copyMessageKind = "";

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

    function coordinatorState() {
      return applyState || coordinator?.state || {};
    }

    function coordinatorApplyReady() {
      const locks = coordinator?.locks || {};
      return coordinator?.ok === true
        && coordinator?.apply_enabled === true
        && coordinator?.read_only === false
        && preview?.coordinator?.apply_blocked === false
        && preview?.validation?.valid !== false
        && !Object.values(locks).some((value) => value === true)
        && !applyBusy;
    }

    function applyStateLabel(value) {
      const labels = {
        idle: "idle",
        validating: "validating reviewed setup…",
        applying: "writing configuration…",
        reloading: "provisioning CAN adapter…",
        verifying: "verifying loaded runtime…",
        restoring: "restoring previous setup…",
        complete: "complete",
        failed: "failed",
      };
      return labels[String(value || "")] || String(value || "waiting…");
    }

    function applyPayload() {
      if (
        !preview
        || preview.read_only !== true
        || preview.apply_available !== false
        || preview.state !== "ready"
        || !preview.target
        || typeof preview.expected_configuration_revision !== "string"
        || typeof preview.target_configuration_revision !== "string"
      ) return null;
      return {
        target: preview.target,
        expected_configuration_revision: preview.expected_configuration_revision,
        target_configuration_revision: preview.target_configuration_revision,
        confirm: true,
      };
    }

    function applyCapabilityMessage() {
      const state = coordinatorState();
      if (applyBusy) return `Apply progress: ${applyStateLabel(state.state)}`;
      if (coordinatorError) return coordinatorError;
      if (coordinator?.apply_enabled !== true) {
        if (state.stage === "restore-unverified") {
          return "A previous setup could not be restored safely. Applying remains blocked until recovery succeeds.";
        }
        return "The privileged apply service is unavailable.";
      }
      if (Object.values(coordinator?.locks || {}).some((value) => value === true)) {
        return "Another Open MMI lifecycle operation is active. Refresh the review before applying.";
      }
      return "Applying restarts the CAN service and verifies the loaded runtime. A failed mutation is restored automatically.";
    }

    function setApplyMessage(text, kind = "") {
      applyMessage = String(text || "");
      applyMessageKind = String(kind || "");
    }

    function setCopyMessage(text, kind = "") {
      copyMessage = String(text || "");
      copyMessageKind = String(kind || "");
    }

    function copyFeedbackTemplate() {
      if (!copyMessage) return "";
      const kind = copyMessageKind || "warning";
      return `<div class="openmmi-config-message ${escapeHtml(kind)}" role="status" aria-live="polite" data-testid="vehicle-setup-copy-feedback">${escapeHtml(copyMessage)}</div>`;
    }

    function customCopyControl(kind, entry) {
      if (entry?.source === "custom") {
        return `<small class="openmmi-vehicle-custom-location">Stored in your user catalogue. Maintained files remain unchanged.</small>`;
      }
      if (entry?.source !== "maintained") return "";
      const label = kind === "vehicle" ? "profile" : "bindings";
      const busy = copyBusyKind === kind;
      const disabled = loading || previewLoading || applyBusy || Boolean(copyBusyKind)
        || entry.valid === false
        || typeof entry.revision !== "string"
        || !entry.revision;
      return `<button type="button" class="openmmi-settings-link openmmi-vehicle-copy-template" data-openmmi-vehicle-setup-copy="${escapeHtml(kind)}" data-testid="vehicle-setup-copy-${escapeHtml(kind)}" ${disabled ? "disabled" : ""}>${busy ? "Creating custom copy…" : `Use maintained ${label} as template`}</button>`;
    }

    function suggestedCustomId(identifier) {
      const base = `${String(identifier || "custom")}-custom`;
      if (base.length <= 64 && IDENTIFIER_RE.test(base)) return base;
      const shortened = `custom-${String(identifier || "item").slice(0, 56)}`;
      return IDENTIFIER_RE.test(shortened) ? shortened : "custom-item";
    }

    async function copyTemplate(kind) {
      const entry = selectedEntry(kind);
      if (entry?.source !== "maintained" || entry.valid === false || typeof entry.revision !== "string") {
        throw new Error("Select a valid maintained catalogue item to use as a template");
      }
      if (typeof windowRef.prompt !== "function") {
        throw new Error("Custom catalogue naming is unavailable");
      }
      const label = kind === "vehicle" ? "profile" : "bindings";
      const response = windowRef.prompt(
        `Choose an id for the new custom ${label}. Use lowercase letters, numbers, hyphens or underscores.`,
        suggestedCustomId(entry.id),
      );
      if (response === null) return null;
      const customId = String(response || "").trim();
      if (!IDENTIFIER_RE.test(customId)) {
        setCopyMessage("Custom ids must start with a lowercase letter or number and use only lowercase letters, numbers, hyphens or underscores.", "error");
        render();
        return null;
      }

      copyBusyKind = kind;
      setCopyMessage(`Creating custom ${label}…`, "warning");
      clearPreview();
      render();
      try {
        const result = await api.postJson(COPY_ENDPOINT, {
          kind: kind === "vehicle" ? "profile" : "bindings",
          id: customId,
          template_source: "maintained",
          template_id: entry.id,
          template_revision: entry.revision,
        }, { usePayloadError: true });
        const previousDraft = draft ? { ...draft } : null;
        snapshot = await api.getJson(ENDPOINT, { usePayloadError: true });
        if (!previousDraft) seedDraft();
        else draft = previousDraft;
        const customKey = identityKey(result?.custom || { source: "custom", id: customId });
        if (!entryFor(catalogue(kind), customKey)) {
          throw new Error("The custom catalogue copy was created but could not be loaded");
        }
        draft[kind] = customKey;
        draftDirty = draftDiffers();
        setCopyMessage(`Custom ${label} ${customId} was created in your user catalogue. The maintained template was not changed.`, "success");
        return result;
      } catch (error) {
        const code = String(error?.payload?.code || "");
        if (code === "template-stale") {
          setCopyMessage("The maintained template changed. Refresh Vehicle Setup and copy it again.", "warning");
        } else if (code === "custom-exists") {
          setCopyMessage("That custom id already exists. Choose a different id.", "warning");
        } else {
          setCopyMessage(error?.message || `Could not create the custom ${label}`, "error");
        }
        throw error;
      } finally {
        copyBusyKind = "";
        render();
      }
    }

    function applyFeedbackTemplate() {
      const state = coordinatorState();
      const stateName = String(state.state || "");
      const active = ACTIVE_APPLY_STATES.has(stateName);
      const message = applyMessage || (active ? `Apply progress: ${applyStateLabel(stateName)}` : "");
      if (!message) return "";
      const kind = applyMessageKind || (active ? "warning" : stateName === "complete" ? "success" : "error");
      const restoration = state.restoration_attempted === true
        ? state.restoration_verified === true
          ? " Previous setup restoration was verified."
          : " Previous setup restoration could not be verified."
        : "";
      return `<div class="openmmi-config-message ${escapeHtml(kind)}" role="status" aria-live="polite" data-testid="vehicle-setup-apply-feedback">${escapeHtml(message)}${escapeHtml(restoration)}</div>`;
    }

    function terminalApplyMessage(state = {}) {
      if (state.state === "complete") return ["Vehicle setup applied and verified.", "success"];
      if (state.stage === "restored" && state.restoration_verified === true) {
        return [`${state.error || "Vehicle setup apply failed"}. The previous setup was restored and verified.`, "error"];
      }
      if (state.stage === "restore-unverified") {
        return [`${state.error || "Vehicle setup apply failed"}. Restoration could not be verified; do not retry until coordinator recovery succeeds.`, "error"];
      }
      return [state.error || "Vehicle setup apply failed", "error"];
    }

    function scheduleApplyPoll() {
      const stateName = String(coordinatorState().state || "");
      const active = ACTIVE_APPLY_STATES.has(stateName);
      const timeoutMs = Math.max(1000, Number(options.applyActionTimeoutMs || 60000));
      if (active && !applyPollDeadline) applyPollDeadline = Date.now() + timeoutMs;
      if (TERMINAL_APPLY_STATES.has(stateName)) applyPollDeadline = 0;
      const recovering = !coordinator && applyPollDeadline > Date.now();
      if (documentRef.hidden || applyPollTimer || applyBusy || (!active && !recovering)) return;
      const pollIntervalMs = Math.max(25, Number(options.applyPollIntervalMs || 250));
      applyPollTimer = windowRef.setTimeout(async () => {
        applyPollTimer = null;
        if (documentRef.hidden) return;
        await refreshCoordinator(false);
        const next = coordinatorState();
        if (TERMINAL_APPLY_STATES.has(String(next.state || "")) && next.state !== "idle") {
          const [message, kind] = terminalApplyMessage(next);
          setApplyMessage(message, kind);
          try {
            snapshot = await api.getJson(ENDPOINT, { usePayloadError: true });
            if (!draftDirty) seedDraft();
          } catch (_) {}
        }
        render();
        scheduleApplyPoll();
      }, pollIntervalMs);
    }

    async function refreshCoordinator(renderAfter = true) {
      try {
        coordinator = await api.getJson(COORDINATOR_ENDPOINT, { usePayloadError: true });
        coordinatorError = "";
        if (coordinator?.state) applyState = coordinator.state;
      } catch (error) {
        coordinator = null;
        coordinatorError = error?.message || "Could not reach the vehicle configuration coordinator";
      }
      scheduleApplyPoll();
      if (renderAfter) render();
      return coordinator;
    }

    function confirmed(messageText) {
      return typeof windowRef.confirm === "function" && windowRef.confirm(messageText) === true;
    }

    async function runApplyAction(body) {
      const pollIntervalMs = Math.max(25, Number(options.applyPollIntervalMs || 250));
      const timeoutMs = Math.max(1000, Number(options.applyActionTimeoutMs || 60000));
      const deadline = Date.now() + timeoutMs;
      let requestDone = false;
      let requestResult = null;
      let requestError = null;
      const request = api.postJson(APPLY_ENDPOINT, body, { usePayloadError: true })
        .then((result) => {
          requestResult = result;
          if (result?.state) applyState = result.state;
          return result;
        })
        .catch((error) => {
          requestError = error;
          if (error?.payload?.state) applyState = error.payload.state;
          return null;
        })
        .finally(() => { requestDone = true; });

      while (Date.now() < deadline) {
        await Promise.resolve();
        if (requestDone) {
          if (requestError) throw requestError;
          if (requestResult?.ok === true && requestResult?.state?.state === "complete") return requestResult;
          throw new Error("Vehicle setup apply returned an invalid result");
        }
        await Promise.race([
          request,
          new Promise((resolve) => windowRef.setTimeout(resolve, pollIntervalMs)),
        ]);
        if (!requestDone) {
          await refreshCoordinator(false);
          render();
        }
      }
      throw new Error("Timed out waiting for vehicle setup apply");
    }

    function applyFailureMessage(error) {
      const code = String(error?.payload?.code || "");
      const message = error?.message || "Vehicle setup apply failed";
      if (code === "stale-preview") {
        return ["The reviewed setup is stale. Review the current selection again before applying.", "warning"];
      }
      if (code === "busy") {
        return ["Another Open MMI lifecycle operation is active. Review again after it finishes.", "warning"];
      }
      if (code === "apply-failed-restored") {
        return [`${message}. The previous setup was restored and verified.`, "error"];
      }
      if (code === "apply-failed-restore-unverified") {
        return [`${message}. Restoration could not be verified; do not retry until coordinator recovery succeeds.`, "error"];
      }
      return [message, "error"];
    }

    async function applyDraft() {
      const body = applyPayload();
      if (!body || !coordinatorApplyReady()) {
        throw new Error("The reviewed vehicle setup is not ready to apply");
      }
      const vehicle = `${identityDisplay("vehicle", body.target.vehicle)} · ${sourceLabel(body.target.vehicle?.source)}`;
      const bindings = `${identityDisplay("bindings", body.target.bindings)} · ${sourceLabel(body.target.bindings?.source)}`;
      const bus = body.target.runtime?.active_bus || "--";
      const interfaceName = body.target.runtime?.buses?.[bus]?.interface || "--";
      if (!confirmed(`Apply ${vehicle} with ${bindings} on ${interfaceName}? The CAN service will restart and the loaded runtime will be verified.`)) {
        return null;
      }

      applyBusy = true;
      applyState = { state: "validating", stage: "submitting", error: "" };
      setApplyMessage("Applying the reviewed vehicle setup…", "warning");
      render();
      try {
        const result = await runApplyAction(body);
        try {
          snapshot = await api.getJson(ENDPOINT, { usePayloadError: true });
          seedDraft();
        } catch (_) {}
        await refreshCoordinator(false);
        clearPreview();
        applyState = result.state;
        setApplyMessage("Vehicle setup applied and verified.", "success");
        return result;
      } catch (error) {
        const failureState = error?.payload?.state && typeof error.payload.state === "object"
          ? error.payload.state
          : null;
        const [message, kind] = applyFailureMessage(error);
        if (String(error?.payload?.code || "") === "stale-preview") clearPreview();
        setApplyMessage(message, kind);
        await refreshCoordinator(false);
        if (failureState) applyState = failureState;
        throw error;
      } finally {
        applyBusy = false;
        render();
      }
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

      const canApply = Boolean(applyPayload()) && coordinatorApplyReady();
      const capabilityKind = canApply ? "warning" : coordinatorError ? "error" : "warning";
      const transaction = coordinatorState();
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
          <div class="openmmi-settings-subhead"><span>Review changes</span><small>confirmed apply</small></div>
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
          ${applyBusy ? `<div class="openmmi-settings-metric openmmi-vehicle-apply-progress" aria-busy="true"><span>Apply progress</span><strong data-testid="vehicle-setup-apply-progress">${escapeHtml(applyStateLabel(transaction.state))}</strong></div>` : ""}
          ${applyFeedbackTemplate()}
          <div class="openmmi-config-message ${capabilityKind}" role="status" data-testid="vehicle-setup-apply-capability">${escapeHtml(applyCapabilityMessage())}</div>
          <div class="openmmi-config-actions openmmi-vehicle-setup-actions">
            <button type="button" class="openmmi-settings-link" data-openmmi-vehicle-setup-preview-close="true" data-testid="vehicle-setup-preview-close" ${applyBusy ? "disabled" : ""}>Back to selection</button>
            <button type="button" class="openmmi-setting-pill is-selected" data-openmmi-vehicle-setup-apply="true" data-testid="vehicle-setup-apply" ${canApply ? "" : "disabled"}>${applyBusy ? "Applying…" : "Apply setup"}</button>
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
        await refreshCoordinator(false);
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
      const canReview = Boolean(previewRequest()) && !loading && !previewLoading && !applyBusy && !copyBusyKind;
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
            <div class="openmmi-vehicle-setup-selector">
              <label for="openMmiVehicleProfile"><strong>Vehicle profile</strong><small>${escapeHtml(validationNote(profile, "Choose a valid profile"))}</small></label>
              <div class="openmmi-vehicle-setup-selection-control">
                <select id="openMmiVehicleProfile" data-openmmi-vehicle-setup-select="vehicle" data-testid="vehicle-setup-profile" ${loading || previewLoading || applyBusy || copyBusyKind ? "disabled" : ""}>
                  ${optionGroups(catalogue("vehicle"), draft.vehicle, activeVehicle)}
                </select>
                ${customCopyControl("vehicle", profile)}
              </div>
            </div>
            <div class="openmmi-vehicle-setup-selector">
              <label for="openMmiVehicleBindings"><strong>Bindings</strong><small>${escapeHtml(validationNote(bindings, "Choose valid bindings"))}</small></label>
              <div class="openmmi-vehicle-setup-selection-control">
                <select id="openMmiVehicleBindings" data-openmmi-vehicle-setup-select="bindings" data-testid="vehicle-setup-bindings" ${loading || previewLoading || applyBusy || copyBusyKind ? "disabled" : ""}>
                  ${optionGroups(catalogue("bindings"), draft.bindings, activeBindings)}
                </select>
                ${customCopyControl("bindings", bindings)}
              </div>
            </div>
          </div>
          ${copyFeedbackTemplate()}

          <div class="openmmi-settings-subhead"><span>CAN input</span><small>profile summary</small></div>
          <div class="openmmi-vehicle-setup-summary">
            <div class="openmmi-settings-metric"><span>Active CAN bus</span><strong data-testid="vehicle-setup-bus">${escapeHtml(bus.name || active.active_bus || "--")}</strong></div>
            <div class="openmmi-settings-metric"><span>CAN adapter</span><strong data-testid="vehicle-setup-interface">${escapeHtml(interfaceText)}</strong></div>
            <div class="openmmi-settings-metric"><span>Expected bitrate</span><strong data-testid="vehicle-setup-bitrate">${escapeHtml(bitrateLabel(bus.bitrate))}</strong></div>
            <div class="openmmi-settings-metric"><span>Active compatibility</span><strong data-testid="vehicle-setup-compatibility">${escapeHtml(compatibilityLabel())}</strong></div>
          </div>

          <div class="openmmi-config-actions openmmi-vehicle-setup-actions">
            <button type="button" class="openmmi-settings-link" data-openmmi-vehicle-setup-refresh="true" data-testid="vehicle-setup-refresh" ${loading || previewLoading || applyBusy || copyBusyKind ? "disabled" : ""}>Refresh status</button>
            <button type="button" class="openmmi-setting-pill" data-openmmi-vehicle-setup-review="true" data-testid="vehicle-setup-review" ${canReview ? "" : "disabled"}>${previewLoading ? "Checking setup…" : preview ? "Refresh review" : changed ? "Review changes" : "Review current setup"}</button>
          </div>
          <p class="openmmi-vehicle-setup-note">Applying requires this exact review and an explicit confirmation. The coordinator verifies the loaded runtime and restores the previous setup after a failed mutation.</p>

          ${preview ? "" : applyFeedbackTemplate()}
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
      setApplyMessage("", "");
      applyState = null;
      render();
      try {
        const next = await api.getJson(ENDPOINT, { usePayloadError: true });
        snapshot = next;
        if (!draft || !draftDirty) seedDraft();
        await refreshCoordinator(false);
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
      const copyButton = event.target?.closest?.("[data-openmmi-vehicle-setup-copy]");
      if (copyButton && !copyButton.disabled) {
        copyTemplate(copyButton.dataset.openmmiVehicleSetupCopy).catch(() => {});
        return;
      }
      const reviewButton = event.target?.closest?.("[data-openmmi-vehicle-setup-review]");
      if (reviewButton && !reviewButton.disabled) {
        reviewDraft().catch(() => {});
        return;
      }
      const applyButton = event.target?.closest?.("[data-openmmi-vehicle-setup-apply]");
      if (applyButton && !applyButton.disabled) {
        applyDraft().catch(() => {});
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
    documentRef.addEventListener("visibilitychange", scheduleApplyPoll);
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
      applyDraft,
      copyTemplate,
      applyPayload,
      applyStateLabel,
      coordinatorApplyReady,
      draftDiffers,
      previewRequest,
      refresh,
      refreshCoordinator,
      render,
      renderActive,
      reviewDraft,
      scheduleApplyPoll,
      setDraft,
      snapshot: () => snapshot,
      draft: () => draft ? { ...draft } : null,
      preview: () => preview,
      coordinator: () => coordinator,
      applyState: () => coordinatorState(),
      template,
    });
  }

  function install(options = {}) {
    return createController(options);
  }

  return Object.freeze({
    ENDPOINT,
    PREVIEW_ENDPOINT,
    APPLY_ENDPOINT,
    COPY_ENDPOINT,
    COORDINATOR_ENDPOINT,
    createController,
    escapeHtml,
    identityFromKey,
    identityKey,
    install,
  });
});
