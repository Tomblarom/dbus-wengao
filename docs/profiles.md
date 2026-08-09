# Device profiles

Profiles describe general converter behaviour; they do not represent a private installation.

## `vehicle-battery-link`

Allows A-to-B and B-to-A operation. Its compatible Venus roles are `alternator` and `dcsystem`.
Its default is `alternator`. The service class remains stable in both directions: power is positive
when the configured system terminal is charged and negative when the Wengao draws from it. This
lets Venus represent A-to-B vehicle charging as an alternator source without misclassifying the
same device as a classic DC load. DVCC remains disabled.

The opposite terminal may optionally be exposed as an auxiliary battery monitor. This is useful
for a vehicle or starter battery that must remain separate from the configured system terminal.
It does not turn that battery into the Venus system battery or a BMS.

## `bidirectional-battery-link`

Allows both directions between arbitrary battery systems. It publishes as `dcsystem` and does
not participate in DVCC.

## `fixed-direction-dc-converter`

Requires exactly one configured `allowed_directions` value and an identical `locked_direction`.
Compatible roles are `dcdc`, `alternator` and `dcsystem`. The `dcsystem` role is appropriate when
the fixed converter is a source or load viewed from the configured system terminal. A runtime
direction conflict invalidates standard current and power paths; the driver never attempts to
correct direction automatically.

## Control policy

`monitor-only` is the default and is not a Venus D-Bus class. Every permission must be false.
`external-dbus` permits only explicitly enabled remote on/off, voltage and current operations.
Voltage/current permissions additionally require configured per-terminal ranges. Direction, mode,
protection, calibration and factory permissions remain rejected.
