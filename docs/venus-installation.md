# Venus OS installation

The package layout and read-only service were validated against Venus OS Large `v3.80~39` on a
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

Each enabled device gets an independent process, restart cycle and log. The configured
`/dev/serial/by-path/...` path is opened with exclusive access. Each process also owns the
corresponding `/var/lock/serial-starter/<tty>` lock for its lifetime, using the same mechanism as
Venus `serial-starter`. This prevents GPS, VE.Direct and other probes from interleaving data on a
configured Wengao port. During activation, the package first invokes Venus' own `stop-tty.sh`
for each exactly resolved configured TTY. This stops an auto-probe that may already own the port;
the Wengao process then keeps the shared lock for its lifetime. The package deliberately does not
redefine global `serial-starter` aliases, because current Venus alias files overwrite one another
and could remove other drivers from the probe list.

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
