# Venus OS D-Bus mapping

The read-only publisher was tested on Venus OS Large `v3.80~39`, where `VeDbusService` supports
and recommends creating the service with `register=False`, adding every path and registering
afterwards.

## Roles

| Configured role | D-Bus class | Mapping |
|---|---|---|
| `alternator` | `com.victronenergy.alternator` | `/Dc/0/*` is the configured system terminal; charging current and power are positive |
| `dcsystem` | `com.victronenergy.dcsystem` | `/Dc/0/*` is the configured system terminal; consumption from the system is positive and charging is negative |
| `dcdc` | `com.victronenergy.dcdc` | `/Dc/In/*` is the physical source and `/Dc/0/*` is the physical destination |

The internal convention is positive power leaving the configured system terminal. Each role
adapter converts that convention to the sign expected by its Victron class.

The direction comes from the observed parity of register `0x0209`: even states are A-to-B and
odd states are B-to-A. Unknown or profile-disallowed states never receive an assumed direction;
standard current and power paths are invalidated until the conflict clears.

## Read-only boundary

All paths are registered with `writeable=False`. No `/Link/*` path is exposed, because those
paths would advertise external/DVCC control which the device has not yet proven safe.

Identity and raw device-specific values are available under `/Wengao/*`. These paths supplement
the standard role paths and do not replace them. When communication is lost:

- `/Connected` becomes `0`;
- `/Alarms/Communication` becomes `2`;
- measurements and raw runtime data become invalid rather than remaining stale;
- the process keeps retrying without changing device settings.

The product ID is currently `0xFFFF` to avoid claiming an assigned Victron product identifier.

