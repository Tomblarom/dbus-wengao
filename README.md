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
alternator power, while a reverse B-to-A transfer remains the same stable service with negative
power. It is therefore not included as a classic DC-load row.

A device may optionally publish its non-system terminal as a separate read-only
`com.victronenergy.battery` monitor. This auxiliary service contains measurements only: it has no
SOC, BMS limits, DVCC paths or control authority. The primary Venus battery monitor must be
selected explicitly before enabling this feature.

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
measurement remains invalid and `/Connected` remains `0`.

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

## Optional GUIv2 load breakdown

For the explicitly supported Venus GUIv2 version, an optional display-only overlay can show the
total DC load and one live power row per DC device directly in the existing overview widget. It
does not change D-Bus roles or device control. The GUI build is strictly version-pinned and has a
separate backup/restore lifecycle; see `docs/gui-v2.md`.

## License

Copyright (C) 2026 dbus-wengao contributors.

This project is licensed under the GNU Affero General Public License v3.0 only. See `LICENSE`.
The optional GUIv2 overlay is derived from Victron Energy GUIv2 and remains under the separate
Victron Energy OS license v1 in `gui-v2/LICENSE.txt`.
