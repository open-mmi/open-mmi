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
    let busy = false;
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

    function systemTemplate() {
      const launcher = snapshot?.launcher || {};
      const defaultUi = launcher.default_ui || "web";
      const startup = launcher.start_at_login !== false;
      const service = launcher.service_active ? "running" : "stopped";
      const reachable = launcher.dashboard_reachable ? "reachable" : "unreachable";
      return `
        <div data-openmmi-system-settings-panel="true">
          <div class="openmmi-settings-panel-head"><span>System</span><small>desktop shell</small></div>
          ${statusBanner()}
          <div class="openmmi-settings-metric"><span>Dashboard service</span><strong>${escapeHtml(service)}</strong></div>
          <div class="openmmi-settings-metric"><span>Health endpoint</span><strong>${escapeHtml(reachable)}</strong></div>
          ${row("Default interface", "Used by the desktop icon and open-mmi-launcher without arguments.",
            pill("Web", defaultUi === "web", 'data-openmmi-launcher-ui="web" data-testid="launcher-default-web"')
            + pill("TUI", defaultUi === "tui", 'data-openmmi-launcher-ui="tui" data-testid="launcher-default-tui"'))}
          ${row("Start at login", "Enable or disable the dashboard systemd user service at login.",
            pill("off", !startup, 'data-openmmi-launcher-startup="false" data-testid="launcher-startup-off"')
            + pill("on", startup, 'data-openmmi-launcher-startup="true" data-testid="launcher-startup-on"'))}
          ${row("Dashboard service", "Restart after changing Jellyfin credentials or to recover the web process.",
            `<button type="button" class="openmmi-setting-pill" data-openmmi-dashboard-restart="true" data-testid="dashboard-restart" ${busy ? "disabled" : ""}>restart</button>`)}
          <button type="button" class="openmmi-settings-link openmmi-config-refresh" data-openmmi-system-refresh="true" ${busy ? "disabled" : ""}>Refresh status</button>
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
              <button type="button" class="openmmi-setting-pill" data-openmmi-jellyfin-test="true" data-testid="jellyfin-test" ${busy ? "disabled" : ""}>test</button>
              <button type="button" class="openmmi-setting-pill is-selected" data-openmmi-jellyfin-save="true" data-testid="jellyfin-save" ${busy ? "disabled" : ""}>save</button>
              <button type="button" class="openmmi-setting-pill" data-openmmi-jellyfin-clear="true" data-testid="jellyfin-clear" ${busy ? "disabled" : ""}>clear</button>
              ${config.restart_required ? `<button type="button" class="openmmi-setting-pill" data-openmmi-dashboard-restart="true" ${busy ? "disabled" : ""}>restart dashboard</button>` : ""}
            </div>
          </form>
        </div>`;
    }

    function renderSystem() {
      const panel = documentRef.querySelector("#openmmiSettingsPanel");
      if (activeSection() !== "system" || !panel) return;
      const html = systemTemplate();
      const missing = !panel.querySelector?.('[data-openmmi-system-settings-panel="true"]');
      if (html !== lastSystemHtml || missing) {
        lastSystemHtml = html;
        panel.innerHTML = html;
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
          lastJellyfinHtml = html;
          host.innerHTML = html;
        }
      }
    }

    function renderActive() {
      if (activeSection() === "system") renderSystem();
      if (activeSection() === "media") renderJellyfin();
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
      renderActive();
      return snapshot;
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
      } else if (target.dataset.openmmiLauncherStartup) {
        await post("/api/system/launcher", { start_at_login: target.dataset.openmmiLauncherStartup === "true" }, "Startup preference saved");
      } else if (target.dataset.openmmiSystemRefresh) {
        await refresh();
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
      refresh,
      renderActive,
      renderJellyfin,
      renderSystem,
      systemTemplate,
      jellyfinTemplate,
    });
  }

  function install(options = {}) {
    return createController(options);
  }

  return Object.freeze({ createController, escapeHtml, install });
});
