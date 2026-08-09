# Safety model

The WG-48BC1500M is a bidirectional converter capable of transferring substantial power.
Incorrect direction, voltage, current or protection settings can damage batteries, wiring and
connected equipment.

## Current implementation boundary

Startup consists of configuration validation and optional registration of explicitly configured
disconnected D-Bus placeholders. The driver then opens the selected serial port, reads identity
data, validates the model and reads measurements. It never writes during startup or polling.
A placeholder contains no valid measurement, and write callbacks remain locked until the live
device identity has been verified.

Normal manual controls are available only after explicit opt-in. Supported writes are remote
on/off (`0x0401`) and terminal voltage/current (`0x081A`, `0x081B`, `0x081D`, `0x081E`). Each
request passes permission, destination-terminal, hardware and configured-range checks. Identical
values are suppressed, writes to a terminal are rate-limited, Modbus echoes are validated and the
device value is read back before success is reported.

The following operations remain unavailable:

- power mode and direction changes;
- protection-limit changes;
- voltage or current calibration;
- factory reset and manufacturer-data restore;
- DVCC.

## Persistent-setting boundary

The specification states that settable parameters survive power loss. Node-RED flows must therefore
be event-driven. Do not send setpoints on a timer, on every measurement update or as an output
node's startup value. The default minimum interval is five seconds per terminal block, but this is
only a guardrail and not an invitation to write periodically.

DVCC additionally requires evidence that the target registers are suitable for frequent
runtime updates and have a documented communication-loss fail-safe.
