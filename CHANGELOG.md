# Changelog

All notable changes will be documented here. The project follows Semantic Versioning once the
first public release is made.

## Unreleased

- Establish the clean-room, read-only driver foundation.
- Add strict fail-closed multi-device configuration and generic profiles.
- Add read-only alternator, dcdc and dcsystem publishing with stale-data invalidation.
- Add a vendored MIT-licensed Tomli fallback for stripped Venus OS Python builds.
- Add isolated daemontools services, persistent `/data/apps` lifecycle scripts and CI workflows.
- Coordinate per-device services with Venus `serial-starter` locks and its official TTY stop helper.
- Publish display metadata consumed by the separately maintained GUIv2 companion fork.
- Order Wengao overview rows by their device-table position in the local configuration.
- Publish vehicle-battery links as stable alternator services by default.
- Add opt-in, range-limited and readback-verified D-Bus controls for Node-RED.
- Add a per-device communication-alarm policy for intentionally optional converters.
- Exit main and log supervisors cleanly when regenerating daemontools services.
- Include alternator-role Wengao devices in the DC-load breakdown with direction-aware power.
- Publish reverse vehicle-battery-link flow only as a DC load, never as a negative alternator input.
- Keep configured auxiliary batteries in Victron's native battery list while unavailable.
- Publish non-system Wengao auxiliary batteries for optional companion-GUI display.
- Add opt-in metadata for a direction-dependent battery source on bidirectional `dcsystem` devices.
- Define DC-load breakdown, terminal rows and directional battery sources as generic profile
  capabilities, and make GUIv2 consume that published profile contract.
- Add an opt-in persistent last-known-voltage display for auxiliary batteries, including live-data
  status and the timestamp of the most recent valid measurement.
- Stop publishing generic `/ErrorCode = 1` values for communication loss, unknown direction or raw
  Wengao faults; Venus interpreted that value as a false battery over-temperature alarm on
  alternator services.
- Add persistent Orion-compatible cumulative and cycle history for every Wengao profile, including
  direction-separated energy totals and generic DC-meter min/max statistics.
