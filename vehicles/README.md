# Maintained vehicle catalogue

Maintained profiles use a human-browsable hierarchy:

```text
vehicles/<brand>/<model>/<generation-platform>/
```

For example:

```text
vehicles/seat/leon/1p-pq35/
```

Folder names are lowercase and filesystem-safe. The folder answers **where the
vehicle belongs**; `metadata.id` is the stable machine identity used by Open MMI.
The exact mapping is declared in [`catalogue.v1.json`](catalogue.v1.json), which
also carries deprecated IDs used by existing installations.

Do not pre-create empty brand or model directories. Copy `_template` when a real
integration starts. A new profile directory represents a genuine CAN/decoder
boundary, not merely a trim, engine, steering side, or market badge.

Each maintained profile contains:

- `config.json` — identity, buses, canonical events and canonical statuses;
- `README.md` — human scope and contribution notes;
- `fixtures/mappings.v1.json` — deterministic CAN replay proof;
- `evidence/` — profile-local captures or qualification artefacts where suitable;
- `notes/` — reverse-engineering notes and provisional findings.

Run the catalogue and replay gates with:

```bash
open-mmi-config vehicle-setup conform --root .
open-mmi-config vehicle-setup replay --root . <profile-id>
```

Raw discovery remains open. Maintained admission is the continuity checkpoint
that turns vehicle-specific hexadecimal data into shared human meaning.
