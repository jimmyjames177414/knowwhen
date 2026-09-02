"""Intervals, N-tracking and minimum detectable effect.

Binding rules come from ``CONTEXT-SPEC-v0.1.md`` §"Statistical reporting rules": always
report an interval, always state N, always report an MDE so that "no difference" and
"underpowered" are distinguishable, and never round a CI away.

Two of those rules — always report a control arm, and pair by item — govern *intervention*
experiments. knowwhen runs a single arm and reports no intervention effect, so it has
nothing to control against; see ``docs/scoring.md``. The pairing rule does bite the moment
two runs are compared, which is what :func:`paired_mde` is for.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

#: Default number of bootstrap resamples. 10 000 per CONTEXT-SPEC.
DEFAULT_RESAMPLES = 10_000

#: Default confidence level.
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with a percentile bootstrap interval over items."""

    point: float
    low: float
    high: float
    n: int
    confidence: float
    resamples: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "point": self.point,
            "low": self.low,
            "high": self.high,
            "n": self.n,
            "confidence": self.confidence,
            "resamples": self.resamples,
        }

    def format(self, *, percent: bool = False, places: int = 3) -> str:
        """Render as ``point [low, high]``. Never collapses to the point alone."""
        scale = 100.0 if percent else 1.0
        suffix = "%" if percent else ""
        return (
            f"{self.point * scale:.{places}f}{suffix} "
            f"[{self.low * scale:.{places}f}, {self.high * scale:.{places}f}]"
        )


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean of an empty sample is undefined; report N instead")
    return sum(values) / len(values)


def stdev(values: list[float]) -> float:
    """Sample standard deviation. Zero for a sample of one, which is honest: one item
    tells you nothing about spread."""
    n = len(values)
    if n < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (n - 1))


def bootstrap_interval(
    values: list[float],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 7,
) -> Interval:
    """Percentile bootstrap over **items**.

    Items are the independent unit — repeats of the same scenario are not independent
    observations — so callers must pass one value per item, already averaged over repeats.
    """
    if not values:
        raise ValueError("cannot bootstrap an empty sample")
    n = len(values)
    point = mean(values)
    if n == 1:
        # One item gives no spread to resample. Return a degenerate interval rather than
        # a fake one, so the report shows [x, x] and the reader can see why.
        return Interval(point, point, point, n, confidence, 0)

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    low = means[max(0, math.floor(alpha * resamples))]
    high = means[min(resamples - 1, math.ceil((1.0 - alpha) * resamples) - 1)]
    return Interval(point, low, high, n, confidence, resamples)


# Two-sided z at alpha=0.05 and one-sided z at power=0.80. Hard-coded because these are
# the only two the report uses, and pulling in scipy for two constants is not worth it.
_Z_ALPHA_TWO_SIDED = 1.959963984540054
_Z_POWER_80 = 0.8416212335729143


def paired_mde(
    values: list[float],
    *,
    power: float = 0.80,
    alpha: float = 0.05,
) -> float:
    """Smallest EAS difference this item set could detect between two models.

    Assumes a paired comparison on the same items, ``alpha=0.05`` two-sided and
    ``power=0.80``. The standard deviation of the paired *difference* is not observable
    from a single run, so it is approximated as ``sqrt(2) * sd(item scores)`` — the value
    it would take if the two runs were uncorrelated. Real runs on the same items are
    positively correlated, so the true MDE is **smaller** than this: treat the number as a
    conservative ceiling, not a measurement.

    ``power`` and ``alpha`` are accepted for documentation and rejected if changed,
    because the z-constants for other values are not carried in this module.
    """
    if abs(power - 0.80) > 1e-9 or abs(alpha - 0.05) > 1e-9:
        raise NotImplementedError(
            "paired_mde only carries z-constants for alpha=0.05, power=0.80; "
            "compute others yourself rather than trusting a wrong constant"
        )
    n = len(values)
    if n < 2:
        return float("nan")
    sd_diff = math.sqrt(2.0) * stdev(values)
    return (_Z_ALPHA_TWO_SIDED + _Z_POWER_80) * sd_diff / math.sqrt(n)
