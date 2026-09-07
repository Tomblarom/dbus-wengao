# Device profiles

Profiles describe general converter behaviour; they do not represent a private installation.

Every profile also declares its GUI presentation capabilities. These capabilities are part of the
public profile contract, not local GUI patches:

| Capability | Meaning |
|---|---|
| `dc-load-breakdown` | publish one normalized DC-load contribution for the device |
| `terminal-rows` | publish the two physical A/B measurement rows |
| `directional-battery-source` | allow the non-system battery to appear as a source while it charges the system terminal |

The first two capabilities are enabled for all built-in profiles. A direction-dependent battery
source is available only to the two battery-link profiles. Instance configuration supplies only
the name, order, offline policy and explicit opt-in; it cannot add a capability missing from its
selected profile.

## `vehicle-battery-link`

Allows A-to-B and B-to-A operation. Its compatible Venus roles are `alternator` and `dcsystem`.
Its default is `alternator`. The service class remains stable in both directions. When the
configured system terminal is charged, the standard alternator paths publish positive source
power. When the Wengao draws from that terminal, those source paths publish zero and the separate
`/Wengao/DcLoadPower` path publishes positive load power. The optional GUIv2 companion can therefore
place the reverse flow under **DC Loads** without presenting a negative alternator input. DVCC
remains disabled.

Presentation capabilities: `dc-load-breakdown`, `terminal-rows` and
`directional-battery-source`. The last capability still requires the `dcsystem` role and an
explicit `[devices.battery_source]` opt-in.

The opposite terminal may optionally be exposed as an auxiliary battery monitor. This is useful
for a vehicle or starter battery that must remain separate from the configured system terminal.
It does not turn that battery into the Venus system battery or a BMS.

The per-instance `display_last_known_voltage` option may retain the auxiliary terminal's most
recent live voltage while a converter sleeps. It is disabled by default and is not a profile
capability because it changes only historical display behavior, not device operation. The cached
value is explicitly marked non-live and never substitutes cached current, power or connectivity.

## `bidirectional-battery-link`

Allows both directions between arbitrary battery systems. It publishes as `dcsystem` and does
not participate in DVCC. An optional `[devices.battery_source]` table can represent the battery on
the non-system terminal as an overview source while it charges the system terminal. The physical
source direction is inferred from `system_terminal`; it is never selected or changed by the
driver. The same device remains a normal positive DC load in the opposite direction.

The source presentation additionally requires the `dcsystem` role and an allowed direction that
charges the configured system terminal. These instance properties cannot substitute for the
profile capability. The presentation is display metadata only and does not create charging logic.

Presentation capabilities: `dc-load-breakdown`, `terminal-rows` and
`directional-battery-source`.

## `fixed-direction-dc-converter`

Requires exactly one configured `allowed_directions` value and an identical `locked_direction`.
Compatible roles are `dcdc`, `alternator` and `dcsystem`. The `dcsystem` role is appropriate when
the fixed converter is a source or load viewed from the configured system terminal. A runtime
direction conflict invalidates standard current and power paths; the driver never attempts to
correct direction automatically.

Presentation capabilities: `dc-load-breakdown` and `terminal-rows`. This profile deliberately
does not allow a direction-dependent battery-source card.

## Control policy

`monitor-only` is the default and is not a Venus D-Bus class. Every permission must be false.
`external-dbus` permits only explicitly enabled remote on/off, voltage and current operations.
Voltage/current permissions additionally require ranges only for terminals that can be a
destination: B for `A-to-B`, A for `B-to-A`, and both for bidirectional operation. The driver checks
every resulting voltage/current pair against the 1500 W hardware rating immediately before a
write. Direction, mode, protection, calibration and factory permissions remain rejected.
