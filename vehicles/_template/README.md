# Vehicle profile template

Use the checked scaffold command from the repository root instead of copying this
directory by hand:

```bash
open-mmi-config vehicle-setup scaffold \
  --root . \
  --brand "Brand" \
  --model "Model" \
  --generation "Generation" \
  --platform "Platform" \
  --year-from 2000 \
  --year-to 2005
```

The values above are placeholders, not supported-vehicle claims. The command:

- derives a safe `vehicles/<brand>/<model>/<generation-platform>/` path;
- creates an experimental, non-claiming `config.json`;
- creates profile-local README, fixtures, evidence and notes guidance;
- registers a collision-free stable profile ID in `vehicles/catalogue.v1.json`;
- refuses path syntax, symlinked parents, existing destinations, duplicate IDs and aliases;
- supports `--dry-run` so the complete plan can be reviewed without mutation.

After scaffolding, replace placeholders only with facts supported by real captures.
A profile does not become a compatibility claim merely because its directory exists.
Candidate and qualified profiles require deterministic replay and reviewable evidence.
