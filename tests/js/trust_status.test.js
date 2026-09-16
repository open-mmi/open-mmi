"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");

const trust = require("../../ui/web_dashboard/static/trust-status.js");

test("known backend trust statuses are preserved", () => {
  for (const status of ["PASS", "FAIL", "UNVERIFIED"]) {
    assert.equal(trust.normalizeStatus(status), status);
  }
});

test("unknown trust status becomes UNVERIFIED", () => {
  assert.equal(trust.normalizeStatus("GREEN"), "UNVERIFIED");
  assert.equal(trust.normalizeStatus(null), "UNVERIFIED");
});

test("model exposes manifest owner and telemetry evidence", () => {
  const model = trust.buildModel({
    status: "PASS",
    report: {
      manifest: {
        available: true,
        policy_generation: 6,
        digest: "sha256:manifest",
        capabilities: {
          "vehicle.can.transmit": {
            policy: "prohibited",
            assurance: "os-enforced",
          },
          "network.external-egress": {
            policy: "declared-purposes-only",
            assurance: "os-enforced",
            purposes: ["media.internet-radio", "updates.release-fetch"],
          },
        },
      },
      telemetry_authorization: {
        authorized: false,
      },
      checks: [
        {
          id: "owner.accepted-release-state",
          status: "PASS",
          summary: "Accepted owner state is valid.",
          evidence: {
            established: true,
            accepted_generation: 6,
            accepted_manifest_digest: "sha256:accepted",
            current_relation: "equivalent",
            evidence_scopes: ["local-authority-state"],
            live_runtime_observation: false,
            hardware_observation: false,
          },
        },
      ],
    },
    error: null,
  });

  assert.equal(model.status, "PASS");
  assert.equal(model.manifest.generation, 6);
  assert.equal(model.manifest.digest, "sha256:manifest");
  assert.equal(model.ownerTrust.established, true);
  assert.equal(model.ownerTrust.generation, 6);
  assert.equal(model.ownerTrust.currentRelation, "equivalent");
  assert.equal(model.telemetry.authorized, false);
  assert.deepEqual(model.checks[0].evidenceScopes, ["local-authority-state"]);
  assert.equal(model.checks[0].liveRuntimeObservation, false);
  assert.equal(model.checks[0].hardwareObservation, false);

  assert.deepEqual(
    model.manifest.capabilities.map((capability) => capability.id),
    ["network.external-egress", "vehicle.can.transmit"],
  );
});

test("missing report remains visibly UNVERIFIED", () => {
  const html = trust.renderPayload({
    status: "UNVERIFIED",
    report: null,
    error: "Trust inspection evidence is unavailable.",
  });

  assert.match(html, /Overall/);
  assert.match(html, /UNVERIFIED/);
  assert.match(html, /Trust inspection evidence is unavailable/);
});

test("rendered checks expose compact scoped evidence cards", () => {
  const html = trust.renderPayload({
    status: "UNVERIFIED",
    report: {
      manifest: {
        available: true,
        policy_generation: 6,
        digest: "sha256:manifest",
        capabilities: {
          "vehicle.can.transmit": {
            policy: "prohibited",
            assurance: "os-enforced",
          },
        },
      },
      telemetry_authorization: { authorized: false },
      checks: [
        {
          id: "capability.vehicle.can.transmit.enforcement",
          status: "PASS",
          summary: "Static contract only.",
          evidence: {
            evidence_scopes: ["static-contract", "deployed-configuration"],
            live_runtime_observation: false,
            hardware_observation: false,
            evidence_dimensions: {
              "declared-policy": "PASS",
              "static-contract": "PASS",
              "runtime-enforcement": "UNVERIFIED",
              "hardware-qualification": "UNVERIFIED",
            },
          },
        },
      ],
    },
  });

  assert.match(html, /openmmi-trust-capability-head/);
  assert.match(html, />os-enforced</);
  assert.match(html, /openmmi-trust-check-card/);
  assert.match(html, /static contract \+ deployed configuration/);
  assert.match(html, /Runtime observation/);
  assert.match(html, /Hardware observation/);
  assert.match(html, />Not observed</);
  assert.match(html, /Evidence dimensions/);
  assert.match(html, /Declared policy/);
  assert.match(html, /Static contract/);
  assert.match(html, /Runtime enforcement/);
  assert.match(html, /Hardware qualification/);
  assert.match(html, /openmmi-trust-status-pass/);
  assert.match(html, /openmmi-trust-status-unverified/);
  assert.doesNotMatch(html, /Dimensions:/);
});

test("legacy report observation metadata remains explicitly unspecified", () => {
  const html = trust.renderPayload({
    status: "UNVERIFIED",
    report: {
      manifest: {
        available: true,
        policy_generation: 6,
        digest: "sha256:manifest",
        capabilities: {},
      },
      telemetry_authorization: { authorized: false },
      checks: [
        {
          id: "legacy.check",
          status: "PASS",
          summary: "Older v1 evidence.",
          evidence: {},
        },
      ],
    },
  });

  assert.match(html, /scope unspecified/);
  assert.match(html, /Runtime observation/);
  assert.match(html, /Hardware observation/);
  assert.match(html, />Unspecified</);
  assert.doesNotMatch(html, /Evidence dimensions/);
  assert.doesNotMatch(html, />Not observed</);
});

test("long manifest digests are compact but retain the full value", () => {
  const digest = `sha256:${"a".repeat(64)}`;
  const html = trust.renderPayload({
    status: "UNVERIFIED",
    report: {
      manifest: {
        available: true,
        policy_generation: 6,
        digest,
        capabilities: {},
      },
      telemetry_authorization: { authorized: false },
      checks: [],
    },
  });

  assert.match(html, /sha256:aaaaaaaa…aaaaaaaa/);
  assert.match(html, new RegExp(`title="${digest}"`));
});

test("rendered trust surface contains no mutation controls", () => {
  const html = trust.renderPayload({
    status: "FAIL",
    report: {
      manifest: {
        available: false,
        capabilities: {},
      },
      telemetry_authorization: {},
      checks: [],
    },
  });

  assert.match(html, /FAIL/);
  assert.doesNotMatch(html, /<button/i);
  assert.doesNotMatch(html, /acknowledge/i);
  assert.doesNotMatch(html, /approve/i);
});

test("frontend trust module uses GET-only local endpoint", () => {
  const source = fs.readFileSync(
    "ui/web_dashboard/static/trust-status.js",
    "utf8",
  );

  assert.match(source, /const ENDPOINT = "\/api\/trust\/status"/);
  assert.match(source, /api\.getJson\(ENDPOINT\)/);

  for (const forbidden of [
    "postJson",
    "localStorage",
    "sessionStorage",
    "http://",
    "https://",
    "accepted_state",
    "transition_gate",
    "activate_acknowledged_expansion",
  ]) {
    assert.equal(
      source.includes(forbidden),
      false,
      `unexpected trust UI authority/dependency: ${forbidden}`,
    );
  }
});
