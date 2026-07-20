# Pull Request

## Summary

Describe what this PR changes.

## Type of Change

- [ ] Backend / daemon
- [ ] Vehicle profile
- [ ] Status mapping
- [ ] Action module
- [ ] UI / dashboard
- [ ] Installer / updater
- [ ] Documentation
- [ ] Tests
- [ ] Other

## Safety Scope

- [ ] This change is passive CAN receive only
- [ ] This change affects local Linux actions
- [ ] This change affects dashboard/status display
- [ ] This change affects install/update/service behaviour
- [ ] This change adds or changes vehicle CAN transmit/control behaviour

If this adds or changes vehicle CAN transmit/control behaviour, explain the safety design and testing plan.

## Vehicle-Specific Data

- [ ] No vehicle-specific CAN knowledge was added to core Python
- [ ] Vehicle-specific CAN data is kept inside `vehicles/<profile>/config.json`
- [ ] Not applicable

## Shared Human Vocabulary — Reuse or Propose

The registry is a continuity checkpoint, not a walled garden. Raw discovery may use
provisional names; maintained profile events must use the shared vocabulary.

- [ ] I confirmed the signal's human meaning rather than guessing from one capture
- [ ] I classified it as a momentary event or persistent status
- [ ] I searched the canonical registry using ordinary human terms
- [ ] I reused an existing descriptor where its meaning matches
- [ ] Any genuinely new descriptor is proposed in this same PR with its contract, docs and tests
- [ ] Canonical names contain no manufacturer, model, CAN ID, ECU abbreviation, Python module or action function
- [ ] Not applicable

Explain any new descriptor and why no existing one fits:

## Testing

Commands run:

```bash
python3 -m py_compile canbusd/core.py canbusd/status_rules.py canbusd/status_bus.py
python3 -m json.tool vehicles/seat_1p/config.json >/dev/null
python3 -m json.tool bindings/default.json >/dev/null
open-mmi-config vehicle-setup events --search "<human meaning>"
python tools/generate_vehicle_event_docs.py --check
bash -n scripts/manage.sh
```

Additional testing:

- [ ] Tested off-car
- [ ] Tested in vehicle while stationary
- [ ] Tested during normal use
- [ ] Not tested on vehicle

## Notes

Add any known limitations, follow-up work, or safety concerns.
