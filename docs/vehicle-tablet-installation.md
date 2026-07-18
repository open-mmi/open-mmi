# Vehicle tablet installation and cooling

Open MMI can remove avoidable software work, but it cannot override the thermal
capacity of a passively cooled tablet inside a hot dashboard. Treat airflow,
shade, power and service access as part of the installation design.

The Surface Pro 1796 used during qualification is one reference system, not a
universal thermal specification. During controlled hot testing it reported a
platform sensor above its active/passive trip, constrained all CPU threads near
400 MHz, became sluggish and suspended charging while AC remained connected.
Cooling restored normal clocks and charging later resumed. A cold-condition
vehicle test behaved normally.

## Safety rules

- Never disable firmware thermal or charging protection.
- Do not continue deliberate heating near reported hot or critical trip points.
- Avoid direct sunlight and direct heater airflow.
- Keep manufacturer vents, buttons, connectors and antenna regions clear.
- Do not place insulating or flammable material against a hot rear casing.
- Account for condensation when directing very cold air at a hot tablet.
- Cooling should work when the browser is closed, the tablet is suspended or
  Open MMI is unavailable.

## Recommended prototype order

Start with airflow before machining a heat spreader:

1. Open-backed mount with a clear rear air gap.
2. One quiet blower moving cabin air across the rear casing.
3. Sealed bottom-intake/top-exhaust duct if uncontrolled airflow is insufficient.
4. A second blower only if one cannot maintain useful margin.
5. Aluminium spreader or shallow heatsink only if fan-only testing remains
   insufficient.

A practical thin path is:

```text
Cabin air intake below the tablet
        -> shallow rear plenum
        -> airflow across the rear casing
        -> top-mounted or remotely ducted blower
        -> exhaust into an open dashboard cavity
```

The exhaust needs a real path away from the intake. A sealed pocket will heat
soak and recirculate warm air.

## Fans and enclosure

For shallow ducts, centrifugal blowers usually tolerate restriction better than
tiny axial fans and can turn the exhaust through 90 degrees.

Design the enclosure so that:

- the intake free area is larger than the blower outlet;
- the plenum perimeter is sealed enough to force the intended flow path;
- channels are broad and low resistance;
- the fan is vibration-isolated and replaceable;
- a coarse removable grille can be cleaned;
- exhaust does not heat the dock, charger or another electronic module;
- the first prototype can be tested before final trim or aluminium machining.

## Optional aluminium spreader

Use a spreader only after measuring the hot regions and proving that airflow
alone is insufficient. Prefer removable thermal pads during prototyping. Do not
load, distort or permanently bond to the tablet casing, and do not cover vents
or antenna regions. Dense fins can make a shallow blower perform worse by
restricting flow.

## Fan control and power

An independent `Off / Auto / On` controller is appropriate during development.
A hardware thermostat can be calibrated against the tablet's reported platform
sensor, but the controller must not assume both temperatures are identical.

Use a fused, regulated vehicle supply. Do not assume the Surface Dock or a dash
USB socket has unlimited spare power. Test charging with the dashboard closed
and open, CAN absent and active, fans off and on, and the tablet both cool and
warm. A larger charger may improve electrical margin but does not replace
cooling; charging itself adds heat.

## Qualification record

For each prototype record:

- intake and exhaust arrangement;
- fan model, voltage and speed;
- cabin and sunlight conditions;
- CPU current/minimum/maximum clock;
- relevant platform temperature and trip margin;
- AC and charging state;
- dashboard and CAN process CPU;
- noise, vibration and test duration.

A successful installation should maintain useful temperature margin during the
expected cabin conditions, avoid sustained minimum-frequency restriction, avoid
recirculation, and continue cooling independently of Open MMI.
