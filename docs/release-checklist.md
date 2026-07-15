# Release checklist

## Automated gates

- [ ] Python 3.9 and current Python CI are green.
- [ ] Unit, Node, Playwright, CSS-cascade, package-content, and dashboard-smoke jobs are green.
- [ ] The wheel installs in a clean environment and all console entry points start.
- [ ] `npm ci` reproduces the browser-test environment from `package-lock.json`.

## Runtime checks

- [ ] Replay representative CAN captures and verify clean startup, reload, interface loss, and shutdown.
- [ ] Exercise dashboard navigation, overlays, settings persistence, and each enabled media provider.
- [ ] Confirm the dashboard remains read-only with respect to vehicle CAN transmission.
- [ ] Confirm loopback binding is retained unless deployment security has been explicitly reviewed.

## Installation checks

- [ ] Test fresh install, desktop `install`, `reinstall`, and `remove`.
- [ ] Test upgrade from the previous `main` checkpoint.
- [ ] Record a rollback tag and procedure.

## Documentation

- [ ] Update changelog and migration notes.
- [ ] Record supported vehicles, tested hardware, known limitations, and security assumptions.
- [ ] Freeze the reviewed commit and merge that exact SHA.
