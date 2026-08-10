# Venus OS installation

The package layout and default read-only service were validated against Venus OS Large `v3.80~39` on a
Raspberry Pi 4. Python 3.12, pyserial 3.5, D-Bus, GLib and a current `VeDbusService` were present;
the standard-library `tomllib` module and SetupHelper were not. The release therefore includes
a small MIT-licensed Tomli fallback and does not require SetupHelper.

## Layout

```text
/data/apps/dbus-wengao/                    application and generated services
/data/setupOptions/WengaoDcdc/config.toml  private local configuration
/var/log/dbus-wengao.<device-id>/           rotating volatile service log
/service/dbus-wengao.<device-id>            daemontools link per enabled device
```

The application never creates `config.toml`. On first enable it copies only the disabled public
example to `/data/setupOptions/WengaoDcdc/config.example.toml`.

## Pull-based release installation

After a release is published, download `install.sh` and invoke it with an immutable tag:

```sh
bash install.sh vX.Y.Z
```

The installer downloads the release archive and its SHA-256 file, verifies the checksum, stages
the new version and atomically replaces only `/data/apps/dbus-wengao`. A failed enable restores
the previous application. Local configuration is outside that directory and remains untouched.

No release exists until it is explicitly approved and tagged.

## Configuration and activation

Copy the disabled example locally, replace every placeholder and validate the device roles,
system terminals, directions and DeviceInstances. Then run:

```sh
/data/apps/dbus-wengao/enable.sh
```

The order of `[[devices]]` tables is also the order used for Wengao rows in the optional overview
overlay. Changing it requires regenerating/restarting the services. Keep `device_instance` stable;
it identifies the Venus service and is not the display-order control.

Leave `control_mode = "monitor-only"` unless external control is deliberately required. See
`node-red.md` for the additional permission and range configuration.

Communication loss is an alarm by default. For a converter that is intentionally absent at times,
use the following per-device override instead of disabling the service or falsifying `/Connected`:

```toml
[devices.alarms]
communication = false
```

Before enabling an auxiliary battery monitor, select the real house/system battery explicitly in
Venus OS under the system battery-monitor setting. Do not leave this setting on automatic: if the
primary battery later disconnects, an auxiliary or starter battery must not become the system
measurement. The auxiliary `device_instance` must also be unused in the `battery` class.

Each enabled device gets an independent process, restart cycle and log. USB adapters must be
configured through their stable `/dev/serial/by-id/...` alias; built-in serial ports may use a
direct `/dev/tty...` path. List the available aliases with:

```sh
ls -l /dev/serial/by-id/
```

The configured path is opened with exclusive access. Each process also owns the
corresponding `/var/lock/serial-starter/<tty>` lock for its lifetime, using the same mechanism as
Venus `serial-starter`. This prevents GPS, VE.Direct and other probes from interleaving data on a
configured Wengao port. During activation, the package first invokes Venus' own `stop-tty.sh`
for each exactly resolved configured TTY. This stops an auto-probe that may already own the port;
the Wengao process then keeps the shared lock for its lifetime. The package deliberately does not
redefine global `serial-starter` aliases, because current Venus alias files overwrite one another
and could remove other drivers from the probe list.

Repeated activation does not call `stop-tty.sh` for a service link already managed by this package;
otherwise the helper would wait for the running Wengao process to release its own lock. A five-second
timeout also bounds the helper on first activation if another serial process does not release the TTY.

Do not copy private aliases into the public repository. Multi-port adapters expose a separate
interface suffix in each alias; assign only the interfaces physically connected to Wengao devices.
Development configurations that still contain `/dev/serial/by-path/...` must be migrated before
activation; validation rejects those aliases.

Useful commands:

```sh
/data/apps/dbus-wengao/restart.sh
/data/apps/dbus-wengao/disable.sh
/data/apps/dbus-wengao/uninstall.sh
```

Disable and uninstall preserve `/data/setupOptions/WengaoDcdc`. Uninstall removes only the fixed
application path `/data/apps/dbus-wengao` after verifying it exactly.

## SetupHelper

`setup`, `version` and `gitHubInfo` are included for optional future SetupHelper integration.
The standalone `/data/apps` lifecycle remains the baseline and works without SetupHelper.
