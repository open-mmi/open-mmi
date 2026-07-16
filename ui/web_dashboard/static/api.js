(function openMmiApiModule(root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.openMmiApi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createOpenMmiApi(root) {
  "use strict";

  function activeFetch() {
    const fetchImpl = root && root.fetch;
    if (typeof fetchImpl !== "function") {
      throw new Error("Fetch API is unavailable");
    }
    return fetchImpl.bind(root);
  }

  function responseError(response, payload, options) {
    const message = options.usePayloadError
      && payload
      && typeof payload === "object"
      && payload.error
      ? String(payload.error)
      : `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    return error;
  }

  async function requestJson(path, init = {}, options = {}) {
    const response = await activeFetch()(path, {
      cache: "no-store",
      ...init,
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      if (!options.allowInvalidJson) throw error;
    }

    if (options.requireOk !== false && !response.ok) {
      throw responseError(response, payload, options);
    }

    return options.includeResponse ? { response, payload } : payload;
  }

  function getJson(path, options = {}) {
    return requestJson(path, {}, options);
  }

  function postJson(path, body, options = {}) {
    return requestJson(path, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      body: JSON.stringify(body),
    }, options);
  }

  return Object.freeze({
    getJson,
    postJson,
    requestJson,
  });
});
