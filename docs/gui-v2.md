# Optional GUIv2 DC-load breakdown

Victron GUIv2 intentionally aggregates all `dcsystem`, `dcload` and `dcdc` services into one
**DC Loads** overview widget. Its native detail page already lists the individual services. The
optional dbus-wengao overlay keeps the aggregate widget but adds a compact live row containing
the device name and power for every detected DC device.

The overview layout follows the pinned Victron `AcWidgetContent` and `ThreePhaseDisplay` patterns:
the normal large primary-colour total remains in its original position, while device names and
right-aligned watt values use Victron's tertiary font and primary/secondary value colours in the
same row style as AC phase summaries. The detail page uses the same offline display policy.

With `[display] unavailable_devices = "zero"`, configured Wengao services remain present with
`/Connected = 0` and are rendered as `0 W`. With `"hide"`, disconnected Wengao rows are filtered
out. Other Victron DC devices retain their native behaviour.

This is a display-only modification. It does not change the Wengao D-Bus services, sign mapping,
permissions or Modbus communication.

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
`vrmlogger`. Browser caches may require a hard reload.

Rollback is explicit:

```sh
/data/apps/dbus-wengao/gui-v2/restore.sh
```

The driver itself continues operating if GUIv2 is restored, unavailable or updated. The optional
overlay is not automatically installed or reapplied during boot or driver updates. A normal
dbus-wengao uninstall restores the recorded original GUI first if this overlay is still active;
it refuses to remove the restore tool when that recovery cannot be completed safely.
