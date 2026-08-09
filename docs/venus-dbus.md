# Venus OS D-Bus mapping

The read-only publisher was tested on Venus OS Large `v3.80~39`, where `VeDbusService` supports
and recommends creating the service with `register=False`, adding every path and registering
afterwards.

Each exported service uses its own private system-bus connection. This is required when one
converter process publishes both its Venus-role service and an auxiliary battery service, because
both `VeDbusService` objects export the root object path `/`.

## Roles

| Configured role | D-Bus class | Mapping |
|---|---|---|
| `alternator` | `com.victronenergy.alternator` | `/Dc/0/*` is the configured system terminal; charging current and power are positive |
| `dcsystem` | `com.victronenergy.dcsystem` | `/Dc/0/*` is the configured system terminal; consumption from the system is positive and charging is negative |
| `dcdc` | `com.victronenergy.dcdc` | `/Dc/In/*` is the physical source and `/Dc/0/*` is the physical destination |

The internal convention is positive power leaving the configured system terminal. Each role
adapter converts that convention to the sign expected by its Victron class.

The direction comes from the observed parity of register `0x0209`: even states are A-to-B and
odd states are B-to-A. Unknown or profile-disallowed states never receive an assumed direction;
standard current and power paths are invalidated until the conflict clears.

## Read-only boundary

All paths are registered with `writeable=False`. No `/Link/*` path is exposed, because those
paths would advertise external/DVCC control which the device has not yet proven safe.

Identity and raw device-specific values are available under `/Wengao/*`. These paths supplement
the standard role paths and do not replace them. When communication is lost:

- `/Connected` becomes `0`;
- `/Alarms/Communication` becomes `2`;
- measurements and raw runtime data become invalid rather than remaining stale;
- the process keeps retrying without changing device settings.

The product ID is currently `0xFFFF` to avoid claiming an assigned Victron product identifier.

## Auxiliary battery monitor

An enabled `[devices.auxiliary_battery]` table creates a second, read-only
`com.victronenergy.battery` service for the configured non-system terminal. Its current and power
are positive while energy enters that battery and negative while energy leaves it. Voltage remains
available whenever communication and the measurement are valid; SOC is deliberately invalid.

The service publishes no `/Info/MaxCharge*`, `/Info/MaxDischarge*`, `/Link/*` or writable paths and
therefore does not advertise BMS or DVCC authority. Nevertheless, Venus can auto-select any battery
monitor as the system measurement. Select the real system battery explicitly in Venus before
enabling an auxiliary monitor. If that selected service disappears, Venus must report the system
battery as unavailable instead of falling back to the auxiliary battery.

## Unavailable-device display

`[display] unavailable_devices = "zero"` registers a validated converter service before the first
successful hardware read. It contains `/Connected = 0`, a communication alarm and no valid
measurements. The GUI uses the separate `/WengaoShowUnavailable` policy path to render `0 W` for
that disconnected row. Standard `/Dc/0/*` values remain invalid, so system calculations never
receive an invented zero measurement. The default `"hide"` retains the original discovery-first
behaviour.
