# Node-RED control

Venus OS Large includes Victron's Node-RED nodes. They read and write D-Bus services directly, so
dbus-wengao does not need an HTTP or MQTT control API.

## Enable one device deliberately

The default remains read-only. For a device that may be controlled manually, set:

```toml
control_mode = "external-dbus"

[devices.permissions]
remote_on_off = true
set_voltage = true
set_current = true
set_direction = false
set_mode = false
set_protection_limits = false
calibration = false
factory_reset = false

[devices.write_limits]
minimum_interval = 5.0
terminal_b_voltage = [48.0, 58.4]
terminal_b_current = [1.0, 25.0]
```

This example applies to terminal B as an allowed destination. Configure only ranges that are safe
for the connected battery and installation. A bidirectional profile needs explicit ranges for both
possible destination terminals when the corresponding permission is enabled.

## Create buttons and setpoint controls

Use a Victron output node, select the Wengao service, and choose one of the writable measurements.
If a custom path is not listed by the editor, use the Victron Custom Control node with the exact
service and path.

| Function | D-Bus path | Payload |
|---|---|---|
| On | `/Mode` | `1` |
| Off | `/Mode` | `4` |
| Terminal A voltage | `/Wengao/Settings/TerminalA/Voltage` | volts, max. two decimals |
| Terminal A current | `/Wengao/Settings/TerminalA/Current` | amperes, max. two decimals |
| Terminal B voltage | `/Wengao/Settings/TerminalB/Voltage` | volts, max. two decimals |
| Terminal B current | `/Wengao/Settings/TerminalB/Current` | amperes, max. two decimals |

Connect Dashboard buttons or validated numeric inputs to these output nodes. Leave the output
node's **Initial Value** empty: the Wengao settings are persistent, and a Node-RED restart must not
cause an unsolicited device write. Do not drive voltage or current from a periodic inject node.

Use Victron input nodes for `/Connected`, the setting path and
`/Wengao/Control/LastResult`. A successful output is reported only after Modbus response validation
and device readback. Rejected values leave the verified setting unchanged and put the reason in
`LastResult` and the dbus-wengao service log.

For direction-aware monitoring, read `/Wengao/TerminalA/SignedCurrent` and
`/Wengao/TerminalB/SignedCurrent`. Positive current charges the system attached to that terminal;
negative current discharges it. These paths are read-only and become invalid if the direction or
live device data is unavailable.

The driver intentionally does not expose direction, charging mode, battery type, protection
limits, calibration, factory reset or DVCC to Node-RED.
