# Protocol

## Verified transport

Read-only observations on WG-48BC1500M devices confirm:

- Modbus RTU at 9600 baud, 8 data bits, no parity and 1 stop bit;
- slave address `1`;
- holding-register reads through function `0x03`;
- CRC16/Modbus with polynomial `0xA001`, low CRC byte first;
- an internal model string `WG-BC1500M` for the commercial WG-48BC1500M variant.

The request for 16 registers starting at `0x0200` is:

```text
01 03 02 00 00 10 45 BE
```

Function `0x06`, function `0x10` and the manufacturer-specific address `0xFF` are not used by
the driver's read-only stages.

## Frame validation

Responses are accepted only if slave address, function, byte count, exact length and CRC match
the request. Exception frames and trailing bytes are rejected. Timeouts retain partial data
only for local diagnostics.

