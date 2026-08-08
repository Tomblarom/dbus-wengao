# Register evidence map

This is an independently written evidence table. It is not a copy of a manufacturer protocol
document. `observed-rs485` means that a read response with a valid CRC was obtained from the
target hardware; it does not by itself authorise writes.

| Address | Access in this driver | Scale | Meaning | Status | Notes |
|---|---|---:|---|---|---|
| `0000–001D` | read | mixed | identity and version block | observed-rs485 | serial-number bytes are redacted from captures |
| `0200` | read | 0.01 V | terminal A voltage | observed-rs485 | two units observed |
| `0201` | read | 0.01 A | terminal A current | observed-rs485 | sign encoding not yet proven |
| `0202` | read | 1 W | terminal A power | observed-rs485 | sign encoding not yet proven |
| `0203` | read | 0.01 V | terminal B voltage | observed-rs485 | two units observed |
| `0204` | read | 0.01 A | terminal B current | observed-rs485 | sign encoding not yet proven |
| `0205` | read | 1 W | terminal B power | observed-rs485 | sign encoding not yet proven |
| `0206–0207` | read | 1 °C | T1/T2 temperatures | observed-rs485 | negative encoding unknown |
| `0208` | read | 1 | power mode | observed-rs485 | enum comes from family evidence |
| `0209` | read | 1 | runtime operating mode | observed-rs485 | exact direction mapping needs tests |
| `020A–020B` | read | bitfield | fault and alarm signals | observed-rs485 | bit meanings remain family-level evidence |
| `020C` | read | 0.01 V | ACC input voltage | observed-rs485, contradictory | BC900M document labels it compensation; hardware values support ACC |
| `020D` | read | 0.01 V | RMT input voltage | observed-rs485, contradictory | BC900M document labels it compensation; hardware values support RMT |
| `020E` | read | 1 °C | ambient/internal temperature | observed-rs485 | negative encoding unknown |
| `020F` | read | 1 | charging state | observed-rs485, contradictory | state `6` observed although family document lists only `0..5` |
| `0400–040A` | none | mixed | control settings | observed by read only | no writes authorised |
| `0800–0833` | none | mixed | calibration, limits and thresholds | observed by read only | device-specific values are not public fixtures |

No register currently has write permission.

