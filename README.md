# dbus-wengao

`dbus-wengao` is an independent Venus OS driver for Wengao WG-48BC1500M
bidirectional DC/DC converters.

The project is in its read-only development phase. It can inspect device identity and
measurements over Modbus RTU, but deliberately provides no register-write operation and no
DVCC control.

## Safety status

- No device writes are performed during startup or polling.
- Factory reset, calibration, direction changes and protection-limit writes are absent.
- WG-BC900M-family documentation is treated as evidence, not as proof for every register.
- Runtime setpoints and DVCC remain blocked until persistence, write endurance and fail-safe
  behaviour have been verified.

See `docs/safety.md` and `docs/register-map.md` before connecting hardware.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

The read-only CLI is intentionally explicit:

```sh
dbus-wengao-read --port /dev/serial/by-path/REPLACE_ME --once
```

Do not commit real port paths, serial numbers, credentials, local configuration or
non-anonymised captures.

## License

Copyright (C) 2026 dbus-wengao contributors.

This project is licensed under the GNU Affero General Public License v3.0 only. See
`LICENSE`.

