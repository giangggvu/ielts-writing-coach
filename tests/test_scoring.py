from decimal import Decimal

import pytest

from app.scoring import overall_band


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        # Examples published on official IELTS / IDP score pages
        ((6.5, 6.5, 5.0, 7.0), "6.5"),  # average 6.25  -> up to next half band
        ((4.0, 4.5, 4.0, 4.0), "4.0"),  # average 4.125 -> down
        ((6.5, 5.5, 6.0, 6.5), "6.0"),  # average 6.125 -> down
        ((3.5, 4.0, 4.0, 4.0), "4.0"),  # average 3.875 -> up to whole band
        # .75 rounds up to the next whole band
        ((7, 7, 7, 6), "7.0"),  # 6.75
        ((6, 6, 6, 7), "6.5"),  # 6.25
        ((6, 6, 6, 6), "6.0"),
        ((6, 7, 6, 7), "6.5"),  # 6.5 stays
        ((6.5, 6.0, 6.0, 6.0), "6.0"),  # 6.125
        ((6.5, 6.5, 6.0, 6.5), "6.5"),  # 6.375 -> nearest half
        ((6.5, 6.5, 7.0, 6.5), "6.5"),  # 6.625 -> nearest half
        ((9, 9, 9, 9), "9.0"),
        ((0, 0, 0, 1), "0.5"),  # 0.25
    ],
)
def test_official_rounding(scores, expected):
    assert overall_band(scores) == Decimal(expected)


def test_needs_four_scores():
    with pytest.raises(ValueError):
        overall_band([6, 6, 6])


def test_rejects_out_of_range():
    with pytest.raises(ValueError):
        overall_band([10, 6, 6, 6])
