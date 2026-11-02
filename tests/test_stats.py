"""Unit tests for the A/B test statistics (run: python -m unittest discover tests)."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
import stats as st  # noqa: E402


class TestStats(unittest.TestCase):
    def test_srm_balanced_split_passes(self):
        self.assertGreater(st.srm_check(50_000, 50_100), 0.05)

    def test_srm_detects_mismatch(self):
        self.assertLess(st.srm_check(50_000, 52_000), 0.001)

    def test_two_proportion_no_difference(self):
        r = st.two_proportion_test(500, 10_000, 500, 10_000)
        self.assertAlmostEqual(r.abs_diff, 0.0)
        self.assertAlmostEqual(r.p_value, 1.0)
        self.assertLess(r.ci_low, 0)
        self.assertGreater(r.ci_high, 0)

    def test_two_proportion_known_value(self):
        # 10% vs 12% with 5,000 per arm: pooled z = 0.02 / 0.006258 = 3.196, p = 0.00139
        r = st.two_proportion_test(500, 5_000, 600, 5_000)
        self.assertAlmostEqual(r.p_value, 0.00139, places=5)

    def test_welch_detects_shift(self):
        rng = np.random.default_rng(1)
        c, t = rng.normal(10, 2, 4_000), rng.normal(10.3, 2, 4_000)
        r = st.welch_test(c, t)
        self.assertLess(r.p_value, 0.001)
        self.assertTrue(r.ci_low < 0.3 < r.ci_high)

    def test_cuped_reduces_variance_with_correlated_covariate(self):
        rng = np.random.default_rng(2)
        x = rng.normal(0, 1, 10_000)
        y = 2 * x + rng.normal(0, 1, 10_000)
        y_adj, theta, red = st.cuped_adjust(y, x)
        self.assertAlmostEqual(theta, 2.0, places=1)
        self.assertGreater(red, 0.75)
        self.assertAlmostEqual(y_adj.mean(), y.mean(), places=6)

    def test_holm_matches_manual(self):
        adj = st.holm_correction([0.01, 0.04, 0.03])
        self.assertEqual([round(a, 4) for a in adj], [0.03, 0.06, 0.06])

    def test_sample_size_and_mde_are_consistent(self):
        n = st.sample_size_per_arm(0.05, 0.10)
        mde = st.minimum_detectable_effect(0.05, n)
        self.assertAlmostEqual(mde, 0.10, delta=0.01)

    def test_bootstrap_ci_contains_true_difference(self):
        rng = np.random.default_rng(3)
        c, t = rng.exponential(3.0, 3_000), rng.exponential(3.5, 3_000)
        lo, hi = st.bootstrap_mean_diff_ci(c, t, n_boot=500)
        self.assertTrue(lo < 0.5 < hi)


if __name__ == "__main__":
    unittest.main()
