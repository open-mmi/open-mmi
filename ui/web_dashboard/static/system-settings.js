(function openMmiSystemSettingsModule(root, factory) {
  const moduleApi = factory(root);
  if (typeof module === "object" && module.exports) module.exports = moduleApi;
  if (root) root.openMmiSystemSettings = moduleApi;
})(typeof globalThis !== "undefined" ? globalThis : this, function createSystemSettingsModule(root) {
  "use strict";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function createController(options = {}) {
    const windowRef = options.window || root;
    const documentRef = options.document || windowRef?.document;
    const api = options.api || windowRef?.openMmiApi;
    if (!windowRef || !documentRef || !api) throw new Error("System settings require window, document and API client");

    let snapshot = null;
    let updateSnapshot = null;
    let busy = false;
    let updateBusy = false;
    let message = "";
    let messageKind = "";
    let lastSystemHtml = "";
    let lastJellyfinHtml = "";
    let jellyfinDraft = null;

    function activeSection() {
      return documentRef.querySelector("[data-openmmi-settings-section].active")?.dataset?.openmmiSettingsSection || "";
    }

    function setMessage(text, kind = "") {
      message = String(text || "");
      messageKind = kind;
      const banner = documentRef.querySelector(".openmmi-config-message[role='status']");
      if (banner) {
        banner.textContent = message;
        banner.hidden = !message;
        banner.className = `openmmi-config-message ${messageKind}`.trim();
        return;
      }
      renderActive();
    }

    function statusBanner() {
      return `<div class="openmmi-config-message ${escapeHtml(messageKind)}" role="status"${message ? "" : " hidden"}>${escapeHtml(message)}</div>`;
    }

    function pill(label, selected, attributes) {
      return `<button type="button" class="openmmi-setting-pill${selected ? " is-selected" : ""}" ${attributes} aria-pressed="${selected ? "true" : "false"}">${escapeHtml(label)}</button>`;
    }

    function row(title, note, controls) {
      return `<div class="openmmi-setting-row"><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(note)}</small></div><div class="openmmi-setting-controls">${controls}</div></div>`;
    }

    function frontendVersionSnapshot() {
      try {
        return windowRef.__openMmiFrontendVersionController?.snapshot?.() || {};
      } catch (_) {
        return {};
      }
    }

    function frontendVersionStateLabel(value) {
      const labels = {
        current: "up to date",
        reloading: "applying update",
        "update-ready": "reload ready",
        "mismatch-after-reload": "reload required",
        reconnecting: "checking…",
        unavailable: "unavailable",
      };
      return labels[String(value || "")] || String(value || "unavailable");
    }

    function updateStateLabel(value) {
      const labels = {
        "not-checked": "not checked",
        "up-to-date": "up to date",
        "update-available": "update available",
        "remote-different": "remote differs",
        "local-ahead": "local source ahead",
        diverged: "source diverged",
        unavailable: "check unavailable",
        blocked: "check blocked",
        "source-unavailable": "source not configured",
        "source-invalid": "source invalid",
      };
      return labels[String(value || "")] || String(value || "unavailable");
    }

    function repositoryStateLabel(value) {
      const labels = {
        ready: "ready",
        dirty: "local changes",
        "source-changed": "source differs from installed",
        detached: "detached HEAD",
        "branch-mismatch": "different branch",
        unavailable: "unavailable",
        unconfigured: "not configured",
        invalid: "invalid configuration",
      };
      return labels[String(value || "")] || String(value || "unavailable");
    }

    function checkedAtLabel(value) {
      const text = String(value || "").trim();
      if (!text) return "never";
      return text.replace("T", " ").replace("+00:00", " UTC");
    }

    function updateCheckMessage(payload) {
      const state = String(payload?.update?.state || "");
      if (state === "up-to-date") return ["Open MMI is up to date", "success"];
      if (state === "update-available") return ["An update is available", "warning"];
      if (["remote-different", "local-ahead", "diverged"].includes(state)) {
        return ["The tracked remote differs; installation direction is not assumed", "warning"];
      }
      if (["blocked", "source-unavailable", "source-invalid"].includes(state)) {
        return [payload?.update?.error || "Update check is blocked", "warning"];
      }
      if (state === "unavailable") return [payload?.update?.error || "Update check is unavailable", "error"];
      return ["Update status refreshed", "success"];
    }

    function systemTemplate() {
      const launcher = snapshot?.launcher || {};
      const version = frontendVersionSnapshot();
      const defaultUi = launcher.default_ui || "web";
      const autostart = launcher.open_at_login === true;
      const reachable = launcher.dashboard_reachable ? "reachable" : "unreachable";
      const loadedVersion = version.loadedId || "--";
      const serverVersion = version.serverId || "--";
      const versionState = frontendVersionStateLabel(version.state);
      const installed = updateSnapshot?.installed || {};
      const update = updateSnapshot?.update || {};
      const source = updateSnapshot?.source || {};
      const installedVersion = installed.version || "--";
      const availableVersion = update.available_version || "--";
      const channel = updateSnapshot?.channel || "unconfigured";
      const updateState = updateStateLabel(update.state || "not-checked");
      const repositoryState = repositoryStateLabel(source.state || "unconfigured");
      const lastChecked = checkedAtLabel(update.checked_at);
      const updateError = update.error
        ? `<p class="openmmi-update-status-note" data-testid="system-update-error">${escapeHtml(update.error)}</p>`
        : "";
      return `
        <div data-openmmi-system-settings-panel="true" data-openmmi-system-settings-ready="true">
          <div class="openmmi-settings-panel-head"><span>System</span><small>desktop shell and updates</small></div>
          ${statusBanner()}
          <div class="openmmi-settings-metric"><span>Dashboard version</span><strong data-testid="system-frontend-version">${escapeHtml(loadedVersion)}</strong></div>
          <div class="openmmi-settings-metric"><span>Server version</span><strong data-testid="system-server-version">${escapeHtml(serverVersion)}</strong></div>
          <div class="openmmi-settings-metric"><span>Frontend state</span><strong data-testid="system-version-state">${escapeHtml(versionState)}</strong></div>
          <div class="openmmi-settings-metric"><span>Health endpoint</span><strong>${escapeHtml(reachable)}</strong></div>
          <div class="openmmi-settings-subhead"><span>Software updates</span><small>read-only visibility</small></div>
          <div data-openmmi-update-status="true">
            <div class="openmmi-settings-metric"><span>Installed version</span><strong data-testid="system-installed-version">${escapeHtml(installedVersion)}</strong></div>
            <div class="openmmi-settings-metric"><span>Channel</span><strong data-testid="system-update-channel">${escapeHtml(channel)}</strong></div>
            <div class="openmmi-settings-metric"><span>Available version</span><strong data-testid="system-available-version">${escapeHtml(availableVersion)}</strong></div>
            <div class="openmmi-settings-metric"><span>Update status</span><strong data-testid="system-update-state">${escapeHtml(updateState)}</strong></div>
            <div class="openmmi-settings-metric"><span>Last checked</span><strong data-testid="system-update-checked-at">${escapeHtml(lastChecked)}</strong></div>
            <div class="openmmi-settings-metric"><span>Repository health</span><strong data-testid="system-update-repository">${escapeHtml(repositoryState)}</strong></div>
            ${updateError}
            <p class="openmmi-update-status-note">Checking is read-only. Installing, channel changes, readiness checks, and rollback are not enabled in this slice.</p>
            <button type="button" class="openmmi-settings-link openmmi-config-refresh" data-openmmi-update-check="true" data-openmmi-requires-dashboard="true" data-testid="system-update-check" ${updateBusy ? "disabled" : ""}>${updateBusy ? "Checking…" : "Check for updates"}</button>
          </div>
          ${row("Default interface", "Used by the desktop icon and open-mmi-launcher without arguments.",
            pill("Web", defaultUi === "web", 'data-openmmi-launcher-ui="web" data-openmmi-requires-dashboard="true" data-testid="launcher-default-web"')
            + pill("TUI", defaultUi === "tui", 'data-openmmi-launcher-ui="tui" data-openmmi-requires-dashboard="true" data-testid="launcher-default-tui"'))}
          ${row("Open Open MMI at login", "Launch the remembered interface after graphical login. The launcher starts the dashboard service when needed.",
            pill("off", !autostart, 'data-openmmi-launcher-autostart="false" data-openmmi-requires-dashboard="true" data-testid="launcher-autostart-off"')
            + pill("on", autostart, 'data-openmmi-launcher-autostart="true" data-openmmi-requires-dashboard="true" data-testid="launcher-autostart-on"'))}
          <button type="button" class="openmmi-settings-link openmmi-config-refresh" data-openmmi-system-refresh="true" data-openmmi-requires-dashboard="true" ${busy ? "disabled" : ""}>Refresh status</button>
        </div>`;
    }

    function effectiveJellyfinConfig() {
      return Object.assign({}, snapshot?.jellyfin || {}, jellyfinDraft || {});
    }

    function jellyfinTemplate() {
      const config = effectiveJellyfinConfig();
      const authMode = config.auth_mode || "username";
      const restartNote = config.restart_required
        ? '<div class="openmmi-config-message warning">Saved credentials differ from the running dashboard. Restart the dashboard to activate them.</div>'
        : "";
      return `
        <div data-openmmi-jellyfin-settings="true">
          <div class="openmmi-settings-panel-head"><span>Jellyfin setup</span><small>server-side credentials</small></div>
          ${statusBanner()}
          ${restartNote}
          <form id="openMmiJellyfinSettingsForm" class="openmmi-config-form" autocomplete="off">
            <label><span>Server URL</span><input name="url" type="url" required value="${escapeHtml(config.url || "")}" placeholder="https://jellyfin.example:8096" data-testid="jellyfin-url"></label>
            <label><span>Authentication</span><select name="auth_mode" data-testid="jellyfin-auth-mode"><option value="username"${authMode === "username" ? " selected" : ""}>Username and password</option><option value="token"${authMode === "token" ? " selected" : ""}>API token</option></select></label>
            <label><span>Username / scope user</span><input name="username" value="${escapeHtml(config.username || "")}" autocomplete="username" data-testid="jellyfin-username"></label>
            <label data-openmmi-jellyfin-secret="password"${authMode === "token" ? " hidden" : ""}><span>Password</span><input name="password" type="password" autocomplete="new-password" value="${escapeHtml(config.password || "")}" placeholder="${config.password_configured ? "Leave blank to keep saved password" : "Required"}" data-testid="jellyfin-password"></label>
            <label data-openmmi-jellyfin-secret="token"${authMode === "token" ? "" : " hidden"}><span>API token</span><input name="token" type="password" autocomplete="off" value="${escapeHtml(config.token || "")}" placeholder="${config.token_configured ? "Leave blank to keep saved token" : "Required"}" data-testid="jellyfin-token"></label>
            <label><span>User ID (optional)</span><input name="user_id" value="${escapeHtml(config.user_id || "")}"></label>
            <label><span>Library ID (optional)</span><input name="library_id" value="${escapeHtml(config.library_id || "")}"></label>
            <div class="openmmi-config-checks">
              <label><input name="insecure_tls" type="checkbox"${config.insecure_tls ? " checked" : ""}> Allow insecure TLS</label>
              <label><input name="allow_global" type="checkbox"${config.allow_global ? " checked" : ""}> Allow legacy global API-key scope</label>
            </div>
            <p class="openmmi-config-secret-note">Passwords and tokens are written to <code>${escapeHtml(config.path || "~/.config/open-mmi/dashboard.env")}</code> with mode 0600. They are never returned to this browser.</p>
            <div class="openmmi-config-actions">
              <button type="button" class="openmmi-setting-pill" data-openmmi-jellyfin-test="true" data-openmmi-requires-dashboard="true" data-testid="jellyfin-test" ${busy ? "disabled" : ""}>test</button>
              <button type="button" class="openmmi-setting-pill is-selected" data-openmmi-jellyfin-save="true" data-openmmi-requires-dashboard="true" data-testid="jellyfin-save" ${busy ? "disabled" : ""}>save</button>
              <button type="button" class="openmmi-setting-pill" data-openmmi-jellyfin-clear="true" data-openmmi-requires-dashboard="true" data-testid="jellyfin-clear" ${busy ? "disabled" : ""}>clear</button>
              ${config.restart_required ? `<button type="button" class="openmmi-setting-pill" data-openmmi-dashboard-restart="true" data-openmmi-requires-dashboard="true" ${busy ? "disabled" : ""}>restart dashboard</button>` : ""}
            </div>
          </form>
        </div>`;
    }

    function renderSystem() {
      const panel = documentRef.querySelector("#openmmiSettingsPanel");
      if (activeSection() !== "system" || !panel) return;
      const html = systemTemplate();
      const missing = !panel.querySelector?.('[data-openmmi-system-settings-ready="true"]');
      if (html !== lastSystemHtml || missing) {
        lastSystemHtml = html;
        panel.innerHTML = html;
      }
    }

    function focusedControlState(host) {
      const active = documentRef.activeElement;
      if (!active || !host?.contains?.(active)) return null;
      return {
        name: String(active.name || ""),
        testid: String(active.dataset?.testid || active.getAttribute?.("data-testid") || ""),
        selectionStart: Number.isInteger(active.selectionStart) ? active.selectionStart : null,
        selectionEnd: Number.isInteger(active.selectionEnd) ? active.selectionEnd : null,
        selectionDirection: active.selectionDirection || "none",
      };
    }

    function restoreFocusedControl(host, state) {
      if (!host || !state) return;
      const controls = Array.from(host.querySelectorAll?.("input, select, textarea, button") || []);
      const control = controls.find((candidate) => (
        (state.testid && String(candidate.dataset?.testid || candidate.getAttribute?.("data-testid") || "") === state.testid)
        || (state.name && String(candidate.name || "") === state.name)
      ));
      if (!control || typeof control.focus !== "function") return;
      try { control.focus({ preventScroll: true }); }
      catch (_) { control.focus(); }
      if (
        state.selectionStart !== null
        && state.selectionEnd !== null
        && typeof control.setSelectionRange === "function"
      ) {
        try { control.setSelectionRange(state.selectionStart, state.selectionEnd, state.selectionDirection); }
        catch (_) {}
      }
    }

    function renderJellyfin() {
      if (activeSection() !== "media") return;
      let host = documentRef.querySelector("#openMmiJellyfinSettingsHost");
      const panel = documentRef.querySelector("#openmmiSettingsPanel");
      if (!host && panel) {
        host = documentRef.createElement("div");
        host.id = "openMmiJellyfinSettingsHost";
        panel.appendChild(host);
      }
      if (host) {
        const html = jellyfinTemplate();
        const missing = !host.querySelector?.('[data-openmmi-jellyfin-settings="true"]');
        if (html !== lastJellyfinHtml || missing) {
          const focusState = focusedControlState(host);
          lastJellyfinHtml = html;
          host.innerHTML = html;
          restoreFocusedControl(host, focusState);
        }
      }
    }

    function renderActive() {
      if (activeSection() === "system") renderSystem();
      if (activeSection() === "media") renderJellyfin();
    }

    async function refreshUpdateStatus() {
      try {
        updateSnapshot = await api.getJson("/api/system/update-status", { usePayloadError: true });
      } catch (error) {
        updateSnapshot = {
          channel: "unavailable",
          installed: { version: "--" },
          source: { state: "unavailable" },
          update: { state: "unavailable", checked_at: null, error: error?.message || "Could not load update status" },
        };
      }
      renderSystem();
      return updateSnapshot;
    }

    async function refresh() {
      try {
        snapshot = await api.getJson("/api/system/settings", { usePayloadError: true });
        message = "";
        messageKind = "";
      } catch (error) {
        message = error?.message || "Could not load local system settings";
        messageKind = "error";
      }
      await refreshUpdateStatus();
      renderActive();
      return snapshot;
    }

    async function checkForUpdates() {
      updateBusy = true;
      renderSystem();
      try {
        updateSnapshot = await api.postJson("/api/system/update-check", { confirm: true }, { usePayloadError: true });
        const [text, kind] = updateCheckMessage(updateSnapshot);
        setMessage(text, kind);
        return updateSnapshot;
      } catch (error) {
        setMessage(error?.message || "Update check failed", "error");
        throw error;
      } finally {
        updateBusy = false;
        renderSystem();
      }
    }

    async function post(path, payload, successMessage, options = {}) {
      busy = true;
      try {
        const result = await api.postJson(path, payload, { usePayloadError: true });
        if (options.clearJellyfinDraft) jellyfinDraft = null;
        if (options.refresh !== false) await refresh();
        setMessage(successMessage, "success");
        return result;
      } catch (error) {
        setMessage(error?.message || "Configuration operation failed", "error");
        throw error;
      } finally {
        busy = false;
      }
    }

    function captureJellyfinDraft() {
      const form = documentRef.querySelector("#openMmiJellyfinSettingsForm");
      if (!form) throw new Error("Jellyfin form is unavailable");
      const data = new windowRef.FormData(form);
      jellyfinDraft = {
        url: data.get("url") || "",
        auth_mode: data.get("auth_mode") || "username",
        username: data.get("username") || "",
        password: data.get("password") || "",
        token: data.get("token") || "",
        user_id: data.get("user_id") || "",
        library_id: data.get("library_id") || "",
        insecure_tls: data.get("insecure_tls") === "on",
        allow_global: data.get("allow_global") === "on",
      };
      return Object.assign({}, jellyfinDraft);
    }

    function jellyfinPayload() {
      return captureJellyfinDraft();
    }

    async function restartAndWait() {
      await api.postJson("/api/system/dashboard/restart", { confirm: true }, { usePayloadError: true });
      setMessage("Dashboard is restarting…", "success");
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await new Promise((resolve) => windowRef.setTimeout(resolve, 250));
        try {
          await api.getJson("/api/health");
          await refresh();
          setMessage("Dashboard restarted", "success");
          return;
        } catch (_) {}
      }
      setMessage("Restart requested; refresh if the dashboard does not reconnect", "warning");
    }

    async function clickHandler(event) {
      const target = event.target.closest?.("button");
      if (!target) return;
      if (target.dataset.openmmiLauncherUi) {
        await post("/api/system/launcher", { default_ui: target.dataset.openmmiLauncherUi }, "Default interface saved");
      } else if (target.dataset.openmmiLauncherAutostart) {
        await post("/api/system/launcher", { open_at_login: target.dataset.openmmiLauncherAutostart === "true" }, "Login launch preference saved");
      } else if (target.dataset.openmmiSystemRefresh) {
        await refresh();
      } else if (target.dataset.openmmiUpdateCheck) {
        await checkForUpdates();
      } else if (target.dataset.openmmiJellyfinTest) {
        await post("/api/system/jellyfin/test", jellyfinPayload(), "Jellyfin connection succeeded", { refresh: false });
      } else if (target.dataset.openmmiJellyfinSave) {
        await post("/api/system/jellyfin", jellyfinPayload(), "Jellyfin settings saved; restart the dashboard to activate them", { clearJellyfinDraft: true });
      } else if (target.dataset.openmmiJellyfinClear) {
        await post("/api/system/jellyfin/clear", { confirm: true }, "Jellyfin credentials cleared", { clearJellyfinDraft: true });
      } else if (target.dataset.openmmiDashboardRestart) {
        busy = true;
        renderActive();
        try { await restartAndWait(); } finally { busy = false; renderActive(); }
      } else if (target.closest?.('[data-openmmi-settings-section="system"], [data-openmmi-settings-section="media"]')) {
        windowRef.requestAnimationFrame(() => refresh());
      }
    }

    async function submitHandler(event) {
      if (event.target?.id !== "openMmiJellyfinSettingsForm") return;
      event.preventDefault();
      await post("/api/system/jellyfin", jellyfinPayload(), "Jellyfin settings saved; restart the dashboard to activate them", { clearJellyfinDraft: true });
    }

    function inputHandler(event) {
      if (!event.target?.closest?.("#openMmiJellyfinSettingsForm")) return;
      try { captureJellyfinDraft(); } catch (_) {}
    }

    function changeHandler(event) {
      if (!event.target?.closest?.("#openMmiJellyfinSettingsForm")) return;
      try { captureJellyfinDraft(); } catch (_) {}
      if (event.target?.name !== "auth_mode") return;
      const mode = event.target.value;
      documentRef.querySelector('[data-openmmi-jellyfin-secret="password"]')?.toggleAttribute("hidden", mode === "token");
      documentRef.querySelector('[data-openmmi-jellyfin-secret="token"]')?.toggleAttribute("hidden", mode !== "token");
    }

    documentRef.addEventListener("click", (event) => { clickHandler(event).catch(() => {}); });
    documentRef.addEventListener("submit", (event) => { submitHandler(event).catch(() => {}); });
    documentRef.addEventListener("input", inputHandler);
    documentRef.addEventListener("change", changeHandler);
    windowRef.addEventListener("openmmi:settingsrender", () => windowRef.requestAnimationFrame(renderActive));
    windowRef.addEventListener("openmmi:frontendversion", () => windowRef.requestAnimationFrame(renderSystem));
    documentRef.addEventListener("DOMContentLoaded", () => refresh());

    const Observer = windowRef.MutationObserver;
    if (typeof Observer === "function") {
      const observer = new Observer(() => {
        if (["system", "media"].includes(activeSection())) renderActive();
      });
      try { observer.observe(documentRef.body, { childList: true, subtree: true }); } catch (_) {}
    }

    return Object.freeze({
      activeSection,
      captureJellyfinDraft,
      jellyfinPayload,
      checkForUpdates,
      refresh,
      refreshUpdateStatus,
      renderActive,
      renderJellyfin,
      renderSystem,
      systemTemplate,
      frontendVersionSnapshot,
      frontendVersionStateLabel,
      updateStateLabel,
      repositoryStateLabel,
      checkedAtLabel,
      jellyfinTemplate,
    });
  }

  function install(options = {}) {
    return createController(options);
  }

  return Object.freeze({ createController, escapeHtml, install });
});
