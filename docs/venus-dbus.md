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
| `alternator` | `com.victronenergy.alternator` | `/Dc/0/*` is the configured system terminal; source current and power are positive while charging it and zero during reverse flow |
| `dcsystem` | `com.victronenergy.dcsystem` | `/Dc/0/*` is the configured system terminal; consumption from the system is positive and charging is negative unless the optional battery-source presentation replaces that negative display value with zero |
| `dcdc` | `com.victronenergy.dcdc` | `/Dc/In/*` is the physical source and `/Dc/0/*` is the physical destination |

`vehicle-battery-link` defaults to `alternator`. The D-Bus service is not renamed when physical
direction changes. For a system on terminal B, A-to-B is positive charging power. During B-to-A,
the standard alternator current and power paths are zero because Victron groups `alternator`
services exclusively with DC inputs. The reverse flow is instead published as a positive
`/Wengao/DcLoadPower` value for the companion GUI's DC Loads view. This avoids both a negative source and D-Bus
identity churn.

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
`/Alarms/Communication` at `0` while disconnected. `/Connected = 0` and invalid measurements
continue to describe the unavailable state accurately.

`/ErrorCode` is not used as a generic communication, direction or Wengao-fault indicator. Victron
assigns class-specific meanings to non-zero values; for example, error `1` on an alternator is
displayed as a battery over-temperature fault. Until individual Wengao fault bits have a verified
mapping to the selected Victron class, `/ErrorCode` remains `0`. The unmodified device values are
available through `/Wengao/FaultBits` and `/Wengao/AlarmBits`, while communication loss uses the
standard `/Alarms/Communication` path.

`/WengaoDisplayOrder` contains the device's position in `config.toml`. It is display metadata,
not a Victron DeviceInstance. The companion GUI sorts Wengao DC-load rows by this value.

The profile contract is published separately so the GUI does not infer presentation from a local
name, a device role or the offline policy:

| Path | Meaning |
|---|---|
| `/WengaoProfile` | selected generic profile ID |
| `/WengaoProfileDcLoadBreakdown` | profile enables the per-device DC-load row |
| `/WengaoProfileTerminalRows` | profile enables the two physical A/B rows |
| `/WengaoProfileDirectionalBatterySource` | profile permits a direction-dependent battery source |
| `/WengaoTerminalRowsOrder` | terminal-table order when the profile enables terminal rows |

`/WengaoDisplayOrder` and `/WengaoTerminalRowsOrder` follow the `[[devices]]` order. They become
invalid when the corresponding profile presentation is unavailable or a hidden device disconnects.

`/Wengao/SystemTerminal` contains the configured physical system side (`A` or `B`). It is static
display metadata and lets the GUI associate the normalized DC-load power with exactly one of the
two terminal rows.

`/Wengao/DcLoadPower` is a non-negative display-only value from the configured system terminal.
It is `0 W` while power enters the system and reports positive power while the converter draws
from the system. In that reverse direction, the alternator service publishes `0 A` and `0 W` on
both its standard output and input-current/power paths. The device therefore contributes only to
the DC-load presentation and never appears as a negative DC input.

`/Wengao/TerminalA/SignedCurrent` and `/Wengao/TerminalB/SignedCurrent` provide the
direction-aware current at each physical terminal. Positive values mean energy is entering, or
charging, the system connected to that terminal. Negative values mean that system is being
discharged. The original `/Wengao/Terminal*/Current` paths remain unsigned device measurements,
so raw protocol data is not altered. Signed current is invalid when the operating direction is
unknown and whenever communication is unavailable.

## Direction-dependent battery source

An enabled `[devices.battery_source]` table is valid only when the selected profile declares
`directional-battery-source`, the instance uses `dcsystem`, and its allowed directions include the
direction that charges `system_terminal`. It publishes these display paths:

| Path | Meaning |
|---|---|
| `/WengaoBatterySourceEnabled` | source presentation is configured |
| `/WengaoBatterySourceName` | configured overview title |
| `/WengaoBatterySourceTerminal` | physical non-system terminal supplying the energy |
| `/WengaoBatterySourceActive` | current measured direction charges the system terminal |
| `/WengaoBatterySourcePower` | positive power delivered at the system terminal while active |

While active, `/Wengao/DcLoadPower`, `/Dc/0/Current` and `/Dc/0/Power` are `0` for this service.
This prevents Venus from presenting the source as a negative DC load. The companion GUIv2 fork instead
uses the positive battery-source power for a source card. In the opposite direction the source
paths become inactive and the normal positive `dcsystem` load measurements resume. Unknown,
disallowed or disconnected directions never activate the source. This feature performs no device
write and does not alter ACC, RMT, mode or direction.

The product ID is currently `0xFFFF` to avoid claiming an assigned Victron product identifier.

## Persistent history

Every converter service exposes the cumulative and cycle paths used by Victron Orion XS devices.
GUIv2 can therefore render its existing **Overall history** and **Charge cycle history** views
without assigning a false Victron ProductId. The companion GUI also enables that standard view for
third-party alternator and generic DC-meter services whenever these history paths are present.

| Path | Meaning |
|---|---|
| `/History/Cumulative/User/OperationTime` | seconds with measured conversion power and valid direction |
| `/History/Cumulative/User/ChargedAh` | total Ah delivered at the physical destination terminal |
| `/History/Cumulative/User/CyclesStarted` | number of detected continuous transfer sessions |
| `/History/Cumulative/User/CyclesCompleted` | sessions ending normally rather than by fault, direction change or disconnect |
| `/History/Cumulative/User/EnergyToSystem` | kWh delivered to `system_terminal` |
| `/History/Cumulative/User/EnergyFromSystem` | kWh delivered while `system_terminal` was the source |
| `/History/Cumulative/User/EnergyAtoB` | destination-side kWh transferred A-to-B |
| `/History/Cumulative/User/EnergyBtoA` | destination-side kWh transferred B-to-A |
| `/History/Cycle/CyclesAvailable` | retained completed cycles, newest first |
| `/History/Cycle/0/*` | active cycle; invalid when no transfer is active |
| `/History/Cycle/1..50/*` | completed cycles with phase time/Ah, voltage, result, direction and energy |

A cycle begins when a profile-allowed direction has more than `1 W` measured transfer power. A
normal stop completes it; a communication loss, direction change or raw device fault terminates it
with the corresponding standard Orion termination reason. Gaps between successful polls are never
integrated. Charge states `1/2`, `3` and `4` count as bulk, absorption and float respectively;
power-supply state `0` and unknown active states remain accounted as storage/other time.

Minimum/maximum configured-system voltage and temperature plus produced/consumed energy are also
published through the standard generic DC-meter `/History/*` paths. This keeps the statistics
available for `dcsystem` profiles as well as `alternator` and `dcdc` profiles.

State is stored atomically in `/data/setupOptions/WengaoDcdc/state/<device-id>-history.json` with
mode `0600`, checkpointed no more than once every five minutes and again on communication loss or
clean shutdown. These writes affect only Venus OS persistent storage. No Modbus history, setting or
EEPROM register is written, and no old energy is invented before the driver was installed.

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
Victron's native battery list. It keeps `/Connected = 0` and normally publishes IEEE `NaN` at
`/Dc/0/Voltage`, which Venus treats as a present battery with an unavailable numeric value. The
default `"hide"` policy invalidates the voltage normally, allowing Victron to remove the
unavailable monitor from its battery list.

`display_last_known_voltage = true` in `[devices.auxiliary_battery]` is an explicit exception for
the voltage display only. Every successful poll records the measured auxiliary-terminal voltage
and Unix timestamp in memory. The state is atomically checkpointed under
`/data/setupOptions/WengaoDcdc/state/` at most every five minutes and again when communication is
lost or the service exits. On a later offline start, `/Dc/0/Voltage` contains the restored value,
while `/Connected = 0`, current and power remain invalid. The state file is local runtime data and
must not be committed.

| Path | Meaning |
|---|---|
| `/Wengao/DisplayLastKnownVoltage` | configured opt-in flag |
| `/Wengao/VoltageIsLive` | `1` only when the current voltage came from a successful live poll |
| `/Wengao/LastKnownVoltage` | last successfully observed voltage |
| `/Wengao/LastLiveDataAt` | Unix timestamp of that successful observation |

## Unavailable-device display

`[display] unavailable_devices = "zero"` registers a validated converter service before the first
successful hardware read. It contains `/Connected = 0` and no valid measurements. Communication
alarm behaviour remains the device's explicit alarm policy. The GUI uses the separate
`/WengaoShowUnavailable` policy path to render `0 W` for that disconnected row. Standard
`/Dc/0/*` values remain invalid, so system calculations never receive an invented zero
measurement. The default `"hide"` retains the original discovery-first behaviour.
