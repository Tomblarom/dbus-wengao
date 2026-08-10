# Venus OS D-Bus mapping

The publisher was tested on Venus OS Large `v3.80~39`, where `VeDbusService` supports
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

`vehicle-battery-link` defaults to `alternator`. The D-Bus service is not renamed when physical
direction changes. For a system on terminal B, A-to-B is positive charging power and B-to-A is
negative power. This follows the Victron alternator model, which can represent the device acting
as a source or a load, and avoids D-Bus identity churn.

The internal convention is positive power leaving the configured system terminal. Each role
adapter converts that convention to the sign expected by its Victron class.

The direction comes from the observed parity of register `0x0209`: even states are A-to-B and
odd states are B-to-A. Unknown or profile-disallowed states never receive an assumed direction;
standard current and power paths are invalidated until the conflict clears.

## Write boundary

All paths remain read-only in the default `monitor-only` mode. With `external-dbus` and the matching
per-device permissions, only these paths become writable:

| Path | Accepted value | Device operation |
|---|---|---|
| `/Mode` | `1` on, `4` off | `0x0401`, inverted device shutdown value |
| `/Wengao/Settings/TerminalA/Voltage` | configured range, 0.01 V | `0x081A` |
| `/Wengao/Settings/TerminalA/Current` | configured range, 0.01 A | `0x081B` |
| `/Wengao/Settings/TerminalB/Voltage` | configured range, 0.01 V | `0x081D` |
| `/Wengao/Settings/TerminalB/Current` | configured range, 0.01 A | `0x081E` |

Only terminals that are destinations in an allowed direction are writable.
`/Wengao/Control/LastResult` reports `ok` or the latest rejection. No `/Link/*` path is exposed,
because those paths would advertise DVCC control.

Identity and raw device-specific values are available under `/Wengao/*`. These paths supplement
the standard role paths and do not replace them. When communication is lost:

- `/Connected` becomes `0`;
- `/Alarms/Communication` becomes `2`;
- measurements and raw runtime data become invalid rather than remaining stale;
- the process keeps retrying without changing device settings.

For an intentionally optional device, `[devices.alarms] communication = false` keeps
`/Alarms/Communication` and the communication-derived `/ErrorCode` at `0` while disconnected.
`/Connected = 0` and invalid measurements continue to describe the unavailable state accurately.

`/WengaoDisplayOrder` contains the device's position in `config.toml`. It is display metadata,
not a Victron DeviceInstance. The GUI overlay sorts Wengao DC-load rows by this value.

`/Wengao/DcLoadPower` is a non-negative display-only value from the configured system terminal.
It is `0 W` while power enters the system and reports positive power while the converter draws
from the system. This lets an alternator-role vehicle-battery link remain a correct Victron source
service while its reverse flow is also visible in the DC-load breakdown.

`/Wengao/TerminalA/SignedCurrent` and `/Wengao/TerminalB/SignedCurrent` provide the
direction-aware current at each physical terminal. Positive values mean energy is entering, or
charging, the system connected to that terminal. Negative values mean that system is being
discharged. The original `/Wengao/Terminal*/Current` paths remain unsigned device measurements,
so raw protocol data is not altered. Signed current is invalid when the operating direction is
unknown and whenever communication is unavailable.

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

With `[display] unavailable_devices = "zero"`, an unavailable auxiliary monitor remains in
Victron's native battery list. It keeps `/Connected = 0` and publishes IEEE `NaN` at
`/Dc/0/Voltage`, which Venus treats as a present battery with an unavailable numeric value. No
voltage is invented and no stale measurement is retained. The default `"hide"` policy invalidates
the voltage normally, allowing Victron to remove the unavailable monitor from its battery list.

## Unavailable-device display

`[display] unavailable_devices = "zero"` registers a validated converter service before the first
successful hardware read. It contains `/Connected = 0` and no valid measurements. Communication
alarm behaviour remains the device's explicit alarm policy. The GUI uses the separate
`/WengaoShowUnavailable` policy path to render `0 W` for that disconnected row. Standard
`/Dc/0/*` values remain invalid, so system calculations never receive an invented zero
measurement. The default `"hide"` retains the original discovery-first behaviour.
