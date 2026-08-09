# dbus-wengao

`dbus-wengao` is an independent Venus OS driver for Wengao WG-48BC1500M
bidirectional DC/DC converters.

The project is in its read-only development phase. It can inspect device identity and
measurements over Modbus RTU and publish them through role-specific Venus OS D-Bus services,
but deliberately provides no register-write operation and no DVCC control.

## Safety status

- No device writes are performed during startup or polling.
- Factory reset, calibration, direction changes and protection-limit writes are absent.
- WG-BC900M-family documentation is treated as evidence, not as proof for every register.
- Runtime setpoints and DVCC remain blocked until persistence, write endurance and fail-safe
  behaviour have been verified.

See `docs/safety.md` and `docs/register-map.md` before connecting hardware.

The current Venus roles are `com.victronenergy.alternator`, `com.victronenergy.dcdc` and
`com.victronenergy.dcsystem`. Monitor-only is a control policy, not a separate D-Bus class.
See `docs/venus-dbus.md` for the role and sign mapping.

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
