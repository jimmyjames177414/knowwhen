"""Intervals, N-tracking and MDE.

The CONTEXT-SPEC rules these enforce: always report an interval, resample items not
trials, state N, report an MDE so a null result is interpretable, never round a CI away.
"""

from __future__ import annotations

import math

import pytest

from knowwhen.stats import Interval, bootstrap_interval, mean, paired_mde, stdev


def test_an_interval_contains_its_point_estimate() -> None:
    values = [0.0, 0.25, 0.5, 0.75, 1.0] * 8
    interval = bootstrap_interval(values, resamples=2000, seed=1)
    assert interval.low <= interval.point <= interval.high
    assert interval.point == pytest.approx(mean(values))
    assert interval.n == len(values)


def test_the_bootstrap_is_seeded_and_reproducible() -> None:
    values = [0.1 * i for i in range(20)]
    first = bootstrap_interval(values, resamples=1000, seed=42)
    second = bootstrap_interval(values, resamples=1000, seed=42)
    assert (first.low, first.high) == (second.low, second.high)
    different = bootstrap_interval(values, resamples=1000, seed=43)
    assert (different.low, different.high) != (first.low, first.high)


def test_more_items_give_a_narrower_interval() -> None:
    pattern = [0.0, 1.0]
    narrow = bootstrap_interval(pattern * 100, resamples=2000, seed=3)
    wide = bootstrap_interval(pattern * 5, resamples=2000, seed=3)
    assert (narrow.high - narrow.low) < (wide.high - wide.low)


def test_a_constant_sample_gives_a_degenerate_but_honest_interval() -> None:
    interval = bootstrap_interval([0.5] * 12, resamples=500, seed=1)
    assert interval.low == interval.high == pytest.approx(0.5)


def test_a_single_item_reports_no_spread_rather_than_a_fake_one() -> None:
    interval = bootstrap_interval([0.4], resamples=5000)
    assert interval.n == 1
    assert interval.resamples == 0
    assert interval.low == interval.high == pytest.approx(0.4)


def test_bootstrapping_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="empty sample"):
        bootstrap_interval([])


def test_mean_of_an_empty_sample_is_an_error_not_zero() -> None:
    with pytest.raises(ValueError, match="undefined"):
        mean([])


def test_formatting_never_drops_the_interval() -> None:
    interval = Interval(point=0.184, low=0.129, high=0.241, n=90, confidence=0.95, resamples=10_000)
    rendered = interval.format()
    assert "[" in rendered and "]" in rendered
    assert rendered == "0.184 [0.129, 0.241]"
    assert interval.format(percent=True, places=1) == "18.4% [12.9, 24.1]"


def test_stdev_of_one_value_is_zero() -> None:
    assert stdev([0.7]) == 0.0
    assert stdev([]) == 0.0


def test_mde_shrinks_as_the_item_count_grows() -> None:
    pattern = [0.0, 0.5, 1.0]
    small = paired_mde(pattern * 5)
    large = paired_mde(pattern * 50)
    assert large < small


def test_mde_is_zero_when_every_item_scores_the_same() -> None:
    """No variance means any difference is detectable, which is true and useless."""
    assert paired_mde([0.6] * 30) == pytest.approx(0.0)


def test_mde_is_undefined_below_two_items() -> None:
    assert math.isnan(paired_mde([0.5]))


def test_mde_refuses_parameters_it_does_not_carry_constants_for() -> None:
    with pytest.raises(NotImplementedError, match="z-constants"):
        paired_mde([0.1, 0.9], power=0.9)


def test_mde_matches_the_hand_computed_formula() -> None:
    values = [0.0, 1.0] * 20
    z_sum = 1.959963984540054 + 0.8416212335729143
    expected = z_sum * math.sqrt(2.0) * stdev(values) / math.sqrt(len(values))
    assert paired_mde(values) == pytest.approx(expected)
