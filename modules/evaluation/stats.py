"""Statistical testing utility — TECHNICAL.md Section 4.C.

Used by all four members whenever reporting any comparison between two
methods/configurations (encoder ablations, generator vs. baselines, etc.).
p < 0.05 is required before either method may be reported as "better" in
any writeup (Section 1.9.5) — this module computes the test, it does not
decide the writeup's wording.
"""

from enum import Enum
from typing import List, Optional

import numpy as np
from pydantic import BaseModel
from scipy import stats


class SignificanceTest(str, Enum):
    WILCOXON = "wilcoxon"
    PAIRED_T_TEST = "paired_t_test"


class StatTestResult(BaseModel):
    mean_a: float
    std_a: float
    mean_b: float
    std_b: float
    n: int
    test_name: SignificanceTest
    statistic: float
    p_value: float
    significant: bool
    lower_mean_is: Optional[str] = None  # "a", "b", or None if exactly equal


def compare_methods(
    results_a: List[float],
    results_b: List[float],
    test: SignificanceTest = SignificanceTest.WILCOXON,
    alpha: float = 0.05,
) -> StatTestResult:
    """Paired significance test between two methods' per-seed results on
    the same chips/seeds — `results_a[i]` and `results_b[i]` must be a
    matched pair (Section 1.9.5), not independent samples.

    Wilcoxon signed-rank by default (config/shared_config.yaml's
    `evaluation.significance_test`); pass `test=SignificanceTest.PAIRED_T_TEST`
    to fall back to a paired t-test, per Section 4.C's "falls back to paired
    t-test if explicitly configured."

    Section 1.9.5 requires >= 5 seeds per configuration for any *reported*
    result, but this function does not itself enforce that minimum, so it
    stays usable for the numeric-correctness unit tests INSTRUCTIONS.md
    Step 1.1 asks for (small, hand-picked lists with a known result) — that
    minimum is a reporting-time rule, not a property of the statistic
    itself. Which mean is "better" is metric-dependent (lower is better for
    HPWL/congestion/runtime, not universally) and left to the caller;
    `lower_mean_is` only reports which mean is arithmetically lower.
    """
    if len(results_a) != len(results_b):
        raise ValueError(f"paired test requires equal-length inputs, got {len(results_a)} vs {len(results_b)}")
    if len(results_a) < 2:
        raise ValueError("need at least 2 paired samples to run a significance test")

    arr_a = np.asarray(results_a, dtype=float)
    arr_b = np.asarray(results_b, dtype=float)

    if test == SignificanceTest.WILCOXON:
        statistic, p_value = stats.wilcoxon(arr_a, arr_b)
    elif test == SignificanceTest.PAIRED_T_TEST:
        statistic, p_value = stats.ttest_rel(arr_a, arr_b)
    else:
        raise ValueError(f"unknown significance test: {test}")

    mean_a, mean_b = float(arr_a.mean()), float(arr_b.mean())
    if mean_a < mean_b:
        lower_mean_is = "a"
    elif mean_b < mean_a:
        lower_mean_is = "b"
    else:
        lower_mean_is = None

    return StatTestResult(
        mean_a=mean_a,
        std_a=float(arr_a.std(ddof=1)),
        mean_b=mean_b,
        std_b=float(arr_b.std(ddof=1)),
        n=len(results_a),
        test_name=test,
        statistic=float(statistic),
        p_value=float(p_value),
        significant=bool(p_value < alpha),
        lower_mean_is=lower_mean_is,
    )
