import pytest

from wengao.profiles import Direction, direction_from_operating_mode


@pytest.mark.parametrize("mode", [0, 2, 4, 6, 8])
def test_even_operating_modes_are_forward(mode: int) -> None:
    assert direction_from_operating_mode(mode) is Direction.A_TO_B


@pytest.mark.parametrize("mode", [1, 3, 5, 7, 9])
def test_odd_operating_modes_are_reverse(mode: int) -> None:
    assert direction_from_operating_mode(mode) is Direction.B_TO_A


@pytest.mark.parametrize("mode", [-1, 10, 0xFFFF])
def test_unknown_operating_mode_has_no_assumed_direction(mode: int) -> None:
    assert direction_from_operating_mode(mode) is None
