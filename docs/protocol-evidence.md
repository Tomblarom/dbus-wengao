# Protocol evidence and clean-room boundary

## Evidence classes

- `documented-bc900m`: stated only in the WG-BC900M family document.
- `documented-wg48bc1500m`: explicitly stated in the WG-48BC1500M specification.
- `app-source-confirmed`: independently inferred from manufacturer-provided app material.
- `observed-rs485`: received from the target hardware with a valid Modbus CRC.
- `experimentally-confirmed`: behaviour deliberately varied and verified on a safe bench.
- `contradictory`: available sources or observations disagree.
- `unknown`: insufficient evidence.

## Public/private split

Manufacturer documents and supplied application sources remain private reference material.
This repository contains only independently written descriptions, code and tests. Identity
frames, unredacted captures, serial numbers, credentials, private configuration, app assets and
foreign source files are excluded.

Two anonymised real-time frames are retained as test evidence. They contain no identity block,
serial number, physical port path or installation-specific name.

