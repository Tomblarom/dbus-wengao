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
- Add an optional, version-pinned GUIv2 overview breakdown for individual DC devices.
- Order Wengao overview rows by their device-table position in the local configuration.
- Publish vehicle-battery links as stable alternator services by default.
- Add opt-in, range-limited and readback-verified D-Bus controls for Node-RED.
- Add a per-device communication-alarm policy for intentionally optional converters.
- Exit main and log supervisors cleanly when regenerating daemontools services.
- Include alternator-role Wengao devices in the DC-load breakdown with direction-aware power.
- Keep configured auxiliary batteries in Victron's native battery list while unavailable.
