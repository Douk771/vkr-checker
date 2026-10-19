import dataclasses

import pytest

from vkr_checker.thresholds import DEFAULT_THRESHOLDS, Thresholds


def test_customer_decided_start_values():
    th = DEFAULT_THRESHOLDS
    assert (th.VOL_MIN, th.VOL_MAX, th.PAGE_TOLERANCE) == (60, 85, 2)
    assert th.CHARS_PER_PAGE == 1800 and th.TBL_WIDTH_TOL_CM == 0.2


def test_thresholds_are_immutable_and_overridable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_THRESHOLDS.VOL_MIN = 1  # type: ignore[misc]
    assert Thresholds(VOL_MIN=50).VOL_MIN == 50
