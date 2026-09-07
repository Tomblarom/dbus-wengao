# dbus-wengao

`dbus-wengao` is an independent Venus OS driver for Wengao WG-48BC1500M
bidirectional DC/DC converters.

The driver inspects device identity and measurements over Modbus RTU and publishes them through
role-specific Venus OS D-Bus services. It is read-only by default. Explicit per-device opt-in can
expose the confirmed remote on/off, voltage and current controls to D-Bus clients such as Node-RED.
DVCC remains disabled.

## Safety status

- No device writes are performed during startup or polling.
- Factory reset, calibration, direction changes and protection-limit writes are absent.
- Normal controls require `control_mode = "external-dbus"`, a separate permission and, for
  setpoints, an installation-specific range. Every write is rate-limited and read back.
- WG-BC900M-family documentation is treated as evidence, not as proof for every register.
- Dynamic or cyclic setpoint control and DVCC remain blocked because these settings are persistent.

See `docs/safety.md` and `docs/register-map.md` before connecting hardware.

The current Venus roles are `com.victronenergy.alternator`, `com.victronenergy.dcdc` and
`com.victronenergy.dcsystem`. Monitor-only is a control policy, not a separate D-Bus class.
See `docs/venus-dbus.md` for the role and sign mapping.

`vehicle-battery-link` defaults to `alternator`: A-to-B charging is published as positive
alternator power. During a reverse B-to-A transfer, the same stable service publishes zero source
power instead of a negative DC input. The optional GUI lists that reverse flow under DC Loads:
A-to-B is `0 W`, while B-to-A is shown as positive consumption from the system battery.

A device may optionally publish its non-system terminal as a separate read-only
`com.victronenergy.battery` monitor. This auxiliary service contains measurements only: it has no
SOC, BMS limits, DVCC paths or control authority. The primary Venus battery monitor must be
selected explicitly before enabling this feature.

With `[display] unavailable_devices = "zero"`, that auxiliary battery remains present in Victron's
native battery list while the converter is offline. By default it stays marked disconnected and
shows an unavailable voltage. An auxiliary monitor can explicitly enable
`display_last_known_voltage`; it then shows the last successfully observed voltage as historical
data, together with its observation time in the companion GUI. Connection state, current and power
remain live-only.

The optional companion GUIv2 fork also adds non-system Wengao auxiliary batteries as
compact voltage rows to Victron's existing overview battery widget. This does not change the
selected system battery or create a second energy-system battery.

Battery-link profiles provide a `directional-battery-source` capability. A compatible `dcsystem`
instance can opt into it through `[devices.battery_source]`, presenting the non-system battery as a
source only while its physical direction charges the configured system terminal. The source card
uses a battery icon and its configured name. During that direction the same converter contributes
`0 W` to DC Loads instead of appearing as a negative load.

Every configured converter also maintains local, persistent operating statistics using the
standard history paths displayed by GUIv2 for Orion XS chargers. The history includes active
operation time, transferred Ah, completed/started cycles, charge-phase times, start/end voltage
and energy separated into A-to-B, B-to-A, to-system and from-system totals. It survives converter
deep sleep and driver restarts, but never writes history data back to the Wengao hardware.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

The read-only CLI is intentionally explicit:

```sh
dbus-wengao-read --port /dev/serial/by-id/REPLACE_ME --once
```

Do not commit real port paths, serial numbers, credentials, local configuration or
non-anonymised captures.

The optional `[display] unavailable_devices` setting is `"hide"` by default. `"zero"` keeps every
configured converter visible while disconnected; the GUI displays `0 W`, while the underlying
converter measurement remains invalid and `/Connected` remains `0`.

The optional GUI orders Wengao load rows by their zero-based position in the `[[devices]]` array.
Reorder those tables in the local `config.toml` to control the display; `device_instance` remains
an independent Venus identity and is not repurposed for sorting.

See [docs/node-red.md](docs/node-red.md) for opt-in on/off and bounded setpoint controls.

## Venus OS installation model

The runtime is installed under `/data/apps/dbus-wengao`. Local device configuration lives at
`/data/setupOptions/WengaoDcdc/config.toml` and is outside the application directory, so updates
and uninstall do not replace it. No service is enabled when that local file is absent.

Tagged releases provide a pull-based installer and SHA-256-verified archive. See
`docs/venus-installation.md`. This development branch has not produced a public release yet.

## Optional GUIv2 overview additions

The separately maintained `Tomblarom/gui-v2` fork can show the
total DC load and one live power row per DC device directly in the existing overview widget. It
can also show configured direction-dependent battery sources. It does not change device control.
Its GUI source, build and deployment lifecycle are deliberately independent of this driver; see
`docs/gui-v2.md` and the fork's `DBUS_WENGAO_INTEGRATION.md`.

## License

Copyright (C) 2026 dbus-wengao contributors.

This project is licensed under the GNU Affero General Public License v3.0 only. See `LICENSE`.
The separate GUIv2 fork remains governed by its Victron Energy OS license v1.
