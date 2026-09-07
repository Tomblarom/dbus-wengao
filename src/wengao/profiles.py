"""Generic converter profiles composed from reusable properties."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    A_TO_B = "A-to-B"
    B_TO_A = "B-to-A"


class Terminal(StrEnum):
    A = "A"
    B = "B"


class VenusRole(StrEnum):
    ALTERNATOR = "alternator"
    DC_SYSTEM = "dcsystem"
    DC_DC = "dcdc"


class ControlMode(StrEnum):
    MONITOR_ONLY = "monitor-only"
    EXTERNAL_DBUS = "external-dbus"


class DvccPolicy(StrEnum):
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class Profile:
    id: str
    default_directions: tuple[Direction, ...]
    direction_must_be_locked: bool
    allowed_venus_roles: frozenset[VenusRole]
    default_venus_role: VenusRole
    direction_controls: frozenset[str]


BUILTIN_PROFILES: dict[str, Profile] = {
    "vehicle-battery-link": Profile(
        id="vehicle-battery-link",
        default_directions=(Direction.A_TO_B, Direction.B_TO_A),
        direction_must_be_locked=False,
        allowed_venus_roles=frozenset({VenusRole.ALTERNATOR, VenusRole.DC_SYSTEM}),
        default_venus_role=VenusRole.ALTERNATOR,
        direction_controls=frozenset({"external-hardware", "software", "device-automatic"}),
    ),
    "bidirectional-battery-link": Profile(
        id="bidirectional-battery-link",
        default_directions=(Direction.A_TO_B, Direction.B_TO_A),
        direction_must_be_locked=False,
        allowed_venus_roles=frozenset({VenusRole.DC_SYSTEM}),
        default_venus_role=VenusRole.DC_SYSTEM,
        direction_controls=frozenset({"external-hardware", "software", "device-automatic"}),
    ),
    "fixed-direction-dc-converter": Profile(
        id="fixed-direction-dc-converter",
        default_directions=(),
        direction_must_be_locked=True,
        allowed_venus_roles=frozenset({VenusRole.DC_DC, VenusRole.ALTERNATOR, VenusRole.DC_SYSTEM}),
        default_venus_role=VenusRole.DC_DC,
        direction_controls=frozenset({"locked"}),
    ),
}


def direction_from_operating_mode(value: int) -> Direction | None:
    """Decode the direction parity documented and observed for register 0x0209."""

    if value in {0, 2, 4, 6, 8}:
        return Direction.A_TO_B
    if value in {1, 3, 5, 7, 9}:
        return Direction.B_TO_A
    return None
