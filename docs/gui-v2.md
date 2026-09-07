# Public GUIv2 integration

The driver publishes standard Victron values plus display metadata for generally usable Wengao
views. The GUI source is maintained in the public
[`Tomblarom/gui-v2`](https://github.com/Tomblarom/gui-v2) fork so that it can be reviewed against
the complete upstream GUI. It is not an installation-specific patch and contains no local device
configuration.

The public integration adds:

- compact non-system Wengao battery voltage rows in the standard battery widget;
- optional last-known auxiliary voltage and observation time in the standard battery page;
- ordered per-device DC-load rows and two terminal rows in the Total table;
- an opt-in, direction-dependent battery source card.
- Orion-compatible overall and cycle history for every Wengao profile, including directional
  energy totals.

All three converter presentations are selected through capabilities published by the configured
device profile. GUIv2 does not infer them from local device names, DeviceInstances or a particular
installation. Instance configuration only supplies the `config.toml` order, offline policy and
optional source title/enable state.

The exact D-Bus contract, anonymous mock configuration and build instructions live in the fork's
`DBUS_WENGAO_INTEGRATION.md`. Reordering `[[devices]]` entries changes `/WengaoDisplayOrder`;
restarting the generated services then updates the order in both DC-load views. The driver's
standard D-Bus behavior does not depend on the GUI fork.

GUI changes use Victron Energy source and therefore remain under the fork's Victron Energy OS
license v1. No GUIv2 source or compiled WebAssembly artifact belongs in this AGPL driver package.

Installation and rollback of a GUI build must be handled as a separate operator action.
Removing or updating `dbus-wengao` does not modify the installed GUI.
