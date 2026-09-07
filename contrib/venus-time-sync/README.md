# Venus OS time synchronization helper

This optional helper is intended for RTC-less Venus OS devices where ConnMan remains in the
`ready` state and therefore never starts its internal NTP synchronization. It is independent of
the Wengao driver and is not enabled by the normal dbus-wengao installation.

The service:

- queries four public European NTP pool names directly via SNTP;
- validates response mode, leap state, stratum and timestamp;
- uses the median of the valid replies;
- corrects the system clock only when the difference is at least 0.5 seconds;
- repeats synchronization every 15 minutes and retries failures every 30 seconds;
- persists the last trusted time as a lower bound for the next offline boot.

It cannot determine elapsed powered-off time without either internet access or a hardware RTC.

Enable it explicitly on Venus OS after dbus-wengao has been installed:

```sh
/data/apps/dbus-wengao/contrib/venus-time-sync/enable.sh
```

Runtime configuration is available through environment variables in a custom service wrapper:
`VENUS_TIME_SERVERS`, `VENUS_TIME_QUERY_TIMEOUT`, `VENUS_TIME_SYNC_INTERVAL`,
`VENUS_TIME_RETRY_INTERVAL`, `VENUS_TIME_SET_THRESHOLD`, and `VENUS_TIME_STATE_DIR`.
