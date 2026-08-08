"""Wilson score interval — conservative win-rate (small-sample guard)."""
from __future__ import annotations

import math

Z95 = 1.959963984540054


def wilson_lower_bound(wins: int, n: int, z: float = Z95) -> float:
    """Lower bound of the Wilson interval. 0.0 for n==0; shrinks toward 0 for small n
    so '3/3' ranks below '30/50'."""
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)
