(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiBluetoothMediaController = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";

  function normalisePlaybackStatus(payload = {}) {
    const status = String(payload?.playback_status || "stopped").toLowerCase();
    return ["playing", "paused", "stopped", "forward-seek", "reverse-seek"].includes(status)
      ? status
      : "stopped";
  }

  function effectivePlaybackStatus(payload = {}, override = null) {
    return override || normalisePlaybackStatus(payload);
  }

  function serverPlaybackStatusChanged(previousStatus, payload = {}) {
    if (previousStatus === null || previousStatus === undefined || previousStatus === "") return false;
    return normalisePlaybackStatus({ playback_status: previousStatus }) !== normalisePlaybackStatus(payload);
  }

  function releaseSharedTransportControls(document) {
    ["#ommiMediaPlay", "#ommiMediaPrev", "#ommiMediaNext", "#ommiMediaStop"]
      .forEach((selector) => {
        const button = document?.querySelector?.(selector);
        if (!button) return;
        button.disabled = false;
        button.setAttribute?.("aria-disabled", "false");
      });
  }

  function bluetoothAdapterDescriptor() {
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
    };
  }

  function installController(options = {}) {
    const window = options.window || root;
    const document = options.document || window?.document;
    const apiClient = options.api || window?.openMmiApi;
    if (!window || !document || !apiClient) {
      throw new Error("Bluetooth media controller requires window, document and API client");
    }

      if (window.__openMmiBluetoothMediaSourceLoaded) return window.openMmiBluetoothMedia;
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
        lastServerPlaybackStatus: null,
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
        if (!active) {
          state.controlBusy = false;
          releaseSharedTransportControls(document);
          return;
        }
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
        const previousServerStatus = state.lastServerPlaybackStatus;
        const nextServerStatus = normalizePlaybackStatus(payload);
        state.lastServerPosition = serverPosition;
        state.lastServerObservedAt = now;
        state.lastServerPlaybackStatus = nextServerStatus;

        // A genuine BlueZ status transition may have come from steering-wheel
        // controls or the connected device itself. Release any dashboard-only
        // optimistic override so the shared play/pause button follows it.
        if (state.playbackOverride && serverPlaybackStatusChanged(previousServerStatus, payload)) {
          state.playbackOverride = null;
          state.playbackOverridePosition = serverPosition;
          state.playbackOverrideStartedAt = now;
        }
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
          const result = await apiClient.postJson(
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
          state.lastServerPlaybackStatus = null;
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
      return window.openMmiBluetoothMedia;
  }

  return {
    bluetoothAdapterDescriptor,
    effectivePlaybackStatus,
    installController,
    serverPlaybackStatusChanged,
    normalisePlaybackStatus,
    releaseSharedTransportControls,
  };
});
