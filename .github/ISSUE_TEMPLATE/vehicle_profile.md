---
name: Vehicle profile
about: Share or request a vehicle profile / CAN mapping
title: "[Vehicle Profile]: "
labels: vehicle-profile
assignees: ""
---

## Vehicle

- Make:
- Model:
- Year:
- Platform/chassis code:
- Region:
- Infotainment/head unit:
- CAN adapter:

## Profile status

- [ ] Requesting help decoding
- [ ] Sharing partial profile
- [ ] Sharing tested profile
- [ ] Updating existing profile

## Tested signals

List any known working signals.

```text
Example:
0x470 byte 1 -> doors
0x531 byte 0 -> lighting.mode
0x621 byte 0 -> handbrake
```

## Config snippet

Paste profile snippets if available.

```json
{
  "rules": [],
  "presence": [],
  "status": []
}
```

## Testing notes

- [ ] Tested off-car
- [ ] Tested stationary
- [ ] Tested during normal use

Describe how it was tested.

## Safety notes

Mention anything uncertain or potentially unsafe.

## Sensitive data

Please do not post full VINs or private personal data.
