# Vehicle tablet cooling and installation guidance

| Field | Value |
| --- | --- |
| Branch | `v1-runtime-hardening` |
| Status | Proposed guidance |
| Scope | Vehicle-installed tablets, with Surface Pro 1796 as the qualification reference |

## Purpose

Open MMI can reduce avoidable software workload, but it cannot override the thermal capacity of a passively cooled tablet installed in a hot dashboard.

This document records the hardware findings from desktop-shell qualification and defines safe installation guidance. It is not a promise that one cooling design fits every tablet or vehicle.

## Reference observation

During a controlled hot-condition test on a Surface Pro 1796:

- a platform thermal zone reached approximately 52.5°C;
- its reported active/passive trip was approximately 48.05°C;
- all four CPU threads were constrained near 400 MHz;
- the UI became sluggish;
- AC remained connected while the battery reported `Not charging`;
- cooling the tablet restored normal clock behaviour;
- charging later resumed automatically without another software change.

A separate cold-condition vehicle test passed. The behaviour is therefore treated as a hardware/environment constraint that application efficiency can reduce but not eliminate in every cabin condition.

## Safety principles

- Never disable firmware thermal or charging protection.
- Stop deliberate heat testing before hot or critical trip points are approached.
- Keep the tablet out of direct heater airflow and direct sunlight where practical.
- Do not place flammable or insulating material against a hot rear casing.
- Do not rely on Open MMI software as the only fan controller.
- Cooling must continue when the browser is closed, the tablet is suspended, or the CPU is already throttled.
- Account for condensation if very cold air is directed onto a hot device in humid conditions.
- Preserve access to power connectors, buttons, wireless antenna areas, and any manufacturer vents.

## Recommended first prototype

Test forced airflow before adding a bonded heat spreader.

Suggested path:

```text
Cabin air intake below the tablet
        -> shallow rear air gap or plenum
        -> airflow across the magnesium rear casing
        -> fan or blower near the top
        -> exhaust into an open dashboard cavity
```

The intake should face the cabin or seats rather than a heat-soaked enclosed dash pocket. The exhaust must have a path away from the intake so warm air does not recirculate.

## Bottom-intake, top-exhaust enclosure

A practical thin installation may use:

- a bottom louvred intake integrated into the bezel;
- a shallow sealed rear plenum;
- vertical flow channels;
- one or two slim blowers at the top edge or deeper inside the dash;
- an exhaust path upward or rearward into a larger open cavity.

Natural convection helps when fans are off, but fan pressure dominates while running. The benefit of bottom-to-top flow is straightforward ducting and good separation between intake and exhaust.

## Fan selection

For a shallow duct, a centrifugal blower is normally preferable to a tiny axial fan because it tolerates flow resistance and can turn the exhaust through 90 degrees.

Selection criteria:

- 5 V or another safely regulated vehicle-compatible supply;
- sufficient static pressure for the chosen grille and plenum;
- replaceable mounting;
- acceptable cabin noise;
- ball or fluid-dynamic bearing where practical;
- speed control for testing;
- no dependence on the Surface USB port if that compromises charging or port availability.

Start with one larger quiet blower where packaging permits. Multiple very small blowers may fit more easily but can be noisier and more sensitive to dust and restriction.

## Enclosure design

- Keep a consistent air gap behind most of the tablet.
- Seal the plenum perimeter so air enters through the intended intake.
- Use broad, low-resistance channels rather than many narrow decorative grooves.
- Make the intake free area larger than the blower outlet area.
- Add a removable coarse grille or mesh without using a dense restrictive filter.
- Isolate fan vibration from the tablet and dashboard trim.
- Make the fan cassette serviceable without removing the whole dashboard where possible.
- Ensure exhaust air does not heat the Surface Dock, charger, or other electronics.

A foamboard, plastic-sheet, or rough 3D-printed duct is sufficient for the first test. The goal is to prove airflow before machining a final enclosure.

## Optional aluminium spreader or heatsink

Add a spreader only if fan-only testing leaves insufficient thermal margin.

Possible stack:

```text
Tablet rear casing
Removable thermal interface at measured hot areas
Thin aluminium spreader
Shallow ribs or channels
Forced-air plenum
Rear enclosure
```

Considerations:

- identify hot regions before placing thermal pads;
- avoid permanent adhesive during prototyping;
- do not load or distort the magnesium casing;
- avoid dense fins that choke a low-profile blower;
- ensure the plate improves transfer to moving air rather than simply adding heat-soak mass;
- keep antenna and manufacturer vent regions unobstructed.

## Fan control

Initial development should use an independent control such as:

```text
Off / Auto / On
```

`Auto` may use a simple thermostat attached to the cooled plate or rear enclosure. Calibrate its trigger against the tablet's reported platform sensor rather than assuming both temperatures are identical.

Open MMI may display thermal state, but software-controlled fan output is deferred. A hardware controller should remain able to cool the tablet during suspend, startup, dashboard failure, or browser shutdown.

## Power

Use a fused, regulated supply appropriate for the vehicle electrical system. Do not assume a dashboard USB socket or Surface Dock port has unlimited spare capacity.

Charging behaviour must be tested with:

- dashboard closed and open;
- CAN absent and active;
- tablet cool and warm;
- fans off and on;
- battery partly discharged;
- any dock accessories connected.

A higher-rated charger may improve power margin but does not replace cooling. Charging itself creates heat, and the tablet may suspend charging as a protection response.

## Qualification procedure

Record:

- intake and exhaust arrangement;
- fan model, voltage, and speed;
- cabin condition;
- CPU current/minimum/maximum clock;
- selected platform temperature and trip margin;
- charging state;
- dashboard and CAN process CPU;
- noise and vibration;
- test duration.

Suggested prototype comparison:

1. Existing mount, no fan.
2. Open-backed mount with one blower.
3. Sealed bottom-intake/top-exhaust duct.
4. Two blowers if one is insufficient.
5. Aluminium spreader plus airflow only if required.

## Success criteria

For the reference Surface installation, the cooling system should:

- keep the relevant platform sensor below its active/passive trip with useful margin during normal dashboard use;
- prevent sustained 400 MHz clock restriction in expected cabin conditions;
- allow normal charging behaviour when charger capacity is otherwise sufficient;
- avoid audible or structural vibration that interferes with vehicle use;
- avoid recirculating exhaust into the intake;
- continue operating independently of Open MMI.

## Promotion after implementation

After the cooling prototype is validated, stable and general guidance should move into a permanent installation document. Surface-specific test values should remain identified as one reference result rather than universal requirements.
