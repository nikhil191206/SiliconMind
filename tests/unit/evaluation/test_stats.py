"""compare_methods numeric-correctness tests — INSTRUCTIONS.md Section 1.1:
"two known lists of numbers with a known significance result", not training
data.
"""

import pytest
from scipy import stats as scipy_stats

from modules.evaluation.stats import SignificanceTest, compare_methods

# b is consistently ~1.8-2 lower than a, paired sample-by-sample -> a clear,
# significant difference under both tests.
_RESULTS_A = [10.0, 12.0, 11.0, 13.0, 10.0, 12.0]
_RESULTS_B = [9.0, 10.0, 9.0, 11.0, 8.0, 10.0]

# Same six values shuffled into pairs with inconsistent sign/magnitude of
# difference -> no stable effect for a paired test to detect.
_NOISE_A = [10.0, 9.9, 10.1, 10.0, 9.95, 10.05]
_NOISE_B = [10.05, 9.95, 10.0, 9.9, 10.1, 10.0]


def test_mean_and_std_hand_computed():
    result = compare_methods(_RESULTS_A, _RESULTS_B)
    assert result.mean_a == pytest.approx(68.0 / 6)
    assert result.mean_b == pytest.approx(57.0 / 6)
    assert result.n == 6
    assert result.lower_mean_is == "b"


def test_wilcoxon_matches_scipy_reference_and_is_significant():
    expected_stat, expected_p = scipy_stats.wilcoxon(_RESULTS_A, _RESULTS_B)
    result = compare_methods(_RESULTS_A, _RESULTS_B, test=SignificanceTest.WILCOXON)
    assert result.test_name == SignificanceTest.WILCOXON
    assert result.statistic == pytest.approx(expected_stat)
    assert result.p_value == pytest.approx(expected_p)
    assert result.significant is True


def test_paired_t_test_matches_scipy_reference():
    expected_stat, expected_p = scipy_stats.ttest_rel(_RESULTS_A, _RESULTS_B)
    result = compare_methods(_RESULTS_A, _RESULTS_B, test=SignificanceTest.PAIRED_T_TEST)
    assert result.test_name == SignificanceTest.PAIRED_T_TEST
    assert result.statistic == pytest.approx(expected_stat)
    assert result.p_value == pytest.approx(expected_p)
    assert result.significant is True


def test_no_stable_difference_is_not_significant():
    result = compare_methods(_NOISE_A, _NOISE_B, test=SignificanceTest.PAIRED_T_TEST)
    assert result.significant is False


def test_mismatched_lengths_rejected():
    with pytest.raises(ValueError):
        compare_methods([1.0, 2.0], [1.0])


def test_too_few_samples_rejected():
    with pytest.raises(ValueError):
        compare_methods([1.0], [2.0])
