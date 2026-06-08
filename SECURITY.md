# Security Policy

## Supported Versions

Security and safety reports should target the current stable backend branch and latest tagged backend release.

At the time of writing, the stable backend line is:

```text
v1.0.0-backend
```

## Reporting a Security or Safety Issue

If you believe you have found a security or safety issue, please do not publish exploit details publicly before the maintainer has had time to review it.

Use GitHub private vulnerability reporting if available, or contact the maintainer through GitHub.

Useful details include:

- affected version, branch, or commit
- operating system
- install method
- whether the issue requires vehicle CAN access
- whether the issue affects local Linux actions, status reporting, install/update, or service permissions
- steps to reproduce, where safe to share
- logs with sensitive information removed

## Vehicle Safety Scope

Open MMI interfaces with vehicle CAN-bus data.

Incorrect configuration or unsafe features may:

- trigger unexpected local Linux actions
- misrepresent vehicle state
- distract the driver
- create unsafe behaviour if connected to critical systems

Open MMI currently focuses on:

- passive CAN receive
- local Linux actions
- status decoding
- dashboard/UI consumers

Open MMI should not add vehicle CAN transmit/control behaviour without:

- a separate safety design
- explicit allowlists
- clear user-facing warnings
- review from maintainers
- extensive off-car and controlled testing

## Sensitive Information

Please avoid posting:

- full VINs
- private locations
- personal information
- credentials
- SSH keys
- complete logs containing sensitive data
- unsafe exploit details

Redact sensitive data before sharing logs or CAN captures.

## Responsible Disclosure

The maintainer will aim to acknowledge valid reports, investigate the issue, and publish a fix or mitigation where practical.

Safety-impacting issues may be handled more conservatively than normal bugs.
