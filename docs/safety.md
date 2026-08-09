# Safety model

The WG-48BC1500M is a bidirectional converter capable of transferring substantial power.
Incorrect direction, voltage, current or protection settings can damage batteries, wiring and
connected equipment.

## Current implementation boundary

The read-only stages expose no function that builds or transmits Modbus functions `0x06` or
`0x10`. Startup consists of configuration validation and optional registration of explicitly
configured disconnected D-Bus placeholders. The driver then opens the selected serial port, reads
identity data, validates the model and reads measurements. A placeholder contains no valid
measurement and cannot write to the converter.

The following operations remain unavailable:

- remote output switching;
- voltage and current setpoints;
- power mode and direction changes;
- protection-limit changes;
- voltage or current calibration;
- factory reset and manufacturer-data restore;
- DVCC.

## Future write gate

Any future write must pass explicit per-device permission, profile compatibility, verified
device capability, hard bounds, rate limiting, suppression of identical values, response
validation and readback. No automatic device write may occur at startup.

DVCC additionally requires evidence that the target registers are suitable for frequent
runtime updates and have a documented communication-loss fail-safe.
