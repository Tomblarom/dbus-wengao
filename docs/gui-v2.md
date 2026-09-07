# Optional GUIv2 overview additions

Victron GUIv2 intentionally aggregates all `dcsystem`, `dcload` and `dcdc` services into one
**DC Loads** overview widget. Its native detail page already lists the individual services. The
optional dbus-wengao overlay keeps the aggregate widget but adds a compact live row containing
the device name and DC-load power for every configured Wengao service, including an alternator-role
vehicle-battery link. The latter remains in Victron's native alternator/source presentation and is
additionally listed here: charging the system battery is shown as `0 W`, while power leaving the
system battery for the other terminal is shown as a positive DC load.

Wengao rows are ordered by the position of their `[[devices]]` table in `config.toml`. The driver
publishes that position through `/WengaoDisplayOrder`, and the overlay uses Victron's existing
`VeQItemChildModel` and `VeQItemSortTableModel` pattern. Reordering the local device tables changes
the row order after the services restart. The same order is used in the **Total** table reached by
opening the DC Loads widget. The detail page owns its live models instead of borrowing models from
the overview page, so navigating away from the overview cannot empty or reorder the table.
`device_instance` remains independent.

The Total table includes every configured Wengao role, including `alternator`, so a vehicle-battery
link remains present when unavailable under the `"zero"` policy. Every device occupies exactly two
rows, named `<device> (A)` and `<device> (B)`, with the physical terminal voltage and signed current.
Their battery-oriented sign convention is charging positive and discharging negative. The
normalized DC-load power is shown only on the configured system-terminal row, so it is never
duplicated. Unknown offline measurements remain invalid; only the configured offline DC-load power
is rendered as `0 W`.

The overview layout follows the pinned Victron `AcWidgetContent` and `ThreePhaseDisplay` patterns:
the normal large primary-colour total remains in its original position, while device names and
right-aligned watt values use Victron's tertiary font and primary/secondary value colours in the
same row style as AC phase summaries. The detail page uses the same offline display policy.

With `[display] unavailable_devices = "zero"`, configured Wengao services remain present with
`/Connected = 0` and are rendered as `0 W`. With `"hide"`, disconnected Wengao rows are filtered
out. Other Victron DC devices retain their native behaviour.

The driver publishes the normalized display value separately as `/Wengao/DcLoadPower`. This does
not change standard role measurements, Venus system calculations, permissions or Modbus
communication.

Victron's standard overview battery widget shows only the selected system battery even when
`com.victronenergy.system/Batteries` contains additional monitors. The overlay keeps that widget
and adds a compact row for each non-system Wengao auxiliary battery. It uses the configured battery
name and Victron's standard small battery font and voltage quantity. An unavailable monitor remains
visible as `-- V`; it is not promoted to system battery and no voltage is fabricated or retained.
Clicking the widget continues to open Victron's native battery list.

## Compatibility boundary

`gui-v2/manifest.json` pins all of the following as one tested unit:

- Victron `gui-v2` tag and immutable commit;
- Venus OS `gui-v2-webassembly` package version;
- the dbus-wengao overlay revision.

The installer refuses any other Venus package version. After a Venus OS update, do not reapply an
old build: validate the new upstream widget, update the manifest and rebuild first.

The overlay is based on public Victron GUIv2 code and is governed by the separate
`gui-v2/LICENSE.txt`. In particular, it is intended only for systems whose core consists of
Victron Energy components. No prebuilt WebAssembly binary is committed to Git.

## Reproducible build

On Ubuntu 22.04 or later, first install the exact requirements documented by the pinned Victron
GUIv2 source. Then run:

```sh
gui-v2/build-wasm.sh
```

The script clones only the pinned tag, verifies its full commit hash, applies the small overlay
and writes these ignored build artifacts:

```text
dist/gui-v2/wasm/
dist/gui-v2/venus-webassembly.zip
dist/gui-v2/venus-webassembly.zip.sha256
```

## Installation and rollback

Copy the verified artifact to Venus OS and run:

```sh
/data/apps/dbus-wengao/gui-v2/install.sh /path/to/venus-webassembly.zip
```

Before replacement, the installer verifies the package version, embedded manifest and uncompressed
WASM checksum. It stores the original web GUI under
`/data/setupOptions/WengaoDcdc/gui-v2/backups/`, then atomically replaces the web files and restarts
`vrmlogger`. The build stamps JavaScript, WebAssembly and its metadata requests with the overlay
revision, preventing a reloaded browser from reusing files from an older overlay. A Remote Console
tab that was already open during installation still has the old WebAssembly in memory and must be
reloaded once; server-side replacement cannot modify code already running in a browser tab.

Rollback is explicit:

```sh
/data/apps/dbus-wengao/gui-v2/restore.sh
```

The driver itself continues operating if GUIv2 is restored, unavailable or updated. The optional
overlay is not automatically installed or reapplied during boot or driver updates. A normal
dbus-wengao uninstall restores the recorded original GUI first if this overlay is still active;
it refuses to remove the restore tool when that recovery cannot be completed safely.
