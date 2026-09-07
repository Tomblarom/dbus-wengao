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

Communication loss raises a Venus alarm by default. An intentionally optional or intermittently
installed device may set `[devices.alarms] communication = false`; this suppresses only the
communication alarm. `/Connected` remains `0`, measurements remain invalid, and raw protocol/device
faults are not suppressed. `/ErrorCode` is never synthesized from communication state, an unknown
direction or raw Wengao fault bits because Victron assigns device-class-specific meanings to its
non-zero values. It remains `0` until an explicit, verified mapping is implemented.

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

## History persistence

Operating history is calculated only from consecutive successful read-only polls. Communication
gaps and converter deep sleep are never extrapolated. The state is written atomically to the local
`/data/setupOptions/WengaoDcdc/state/` directory at a rate-limited interval and once during a clean
shutdown. It is not stored on the converter and cannot trigger a Modbus write, change a setpoint or
alter the converter's autonomous charging logic.
