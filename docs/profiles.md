# Device profiles

Profiles describe general converter behaviour; they do not represent a private installation.

## `vehicle-battery-link`

Allows A-to-B and B-to-A operation. Its compatible Venus roles are `alternator` and `dcsystem`.
DVCC remains disabled until volatile setpoints, write endurance and fail-safe behaviour are
proven.

## `bidirectional-battery-link`

Allows both directions between arbitrary battery systems. It publishes as `dcsystem` and does
not participate in DVCC.

## `fixed-direction-dc-converter`

Requires exactly one configured `allowed_directions` value and an identical `locked_direction`.
Compatible roles are `dcdc` and `alternator`. A runtime direction conflict invalidates standard
current and power paths; the driver never attempts to correct direction automatically.

## Monitor-only

`monitor-only` is the current control mode for every profile. It is not a Venus D-Bus class.
Every device permission must remain false and configuration validation rejects any enabled
write permission.

