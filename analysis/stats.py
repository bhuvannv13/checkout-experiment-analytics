"""Statistical helpers for A/B test analysis (numpy/scipy only)."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import stats


@dataclass
class TestResult:
    metric: str
    control: float
    treatment: float
    abs_diff: float
    rel_lift: float
    ci_low: float
    ci_high: float
    p_value: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def srm_check(n_control: int, n_treatment: int, expected_split: float = 0.5) -> float:
    """Sample-ratio-mismatch chi-square test. Returns the p-value
    (a very small p-value, e.g. < 0.001, means the randomisation is suspect)."""
    total = n_control + n_treatment
    expected = [total * expected_split, total * (1 - expected_split)]
    return float(stats.chisquare([n_control, n_treatment], expected).pvalue)


def two_proportion_test(x_c: int, n_c: int, x_t: int, n_t: int, alpha: float = 0.05,
                        metric: str = "conversion_rate") -> TestResult:
    """Two-sided z-test for a difference in proportions with a Wald CI on the difference."""
    p_c, p_t = x_c / n_c, x_t / n_t
    p_pool = (x_c + x_t) / (n_c + n_t)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t))
    z = (p_t - p_c) / se_pool
    p = 2 * stats.norm.sf(abs(z))
    se = np.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    zc = stats.norm.ppf(1 - alpha / 2)
    d = p_t - p_c
    return TestResult(metric, p_c, p_t, d, d / p_c, d - zc * se, d + zc * se, float(p))


def welch_test(c: np.ndarray, t: np.ndarray, alpha: float = 0.05,
               metric: str = "revenue_per_user") -> TestResult:
    """Welch's t-test for a difference in means (unequal variances)."""
    c, t = np.asarray(c, float), np.asarray(t, float)
    res = stats.ttest_ind(t, c, equal_var=False)
    d = t.mean() - c.mean()
    se = np.sqrt(c.var(ddof=1) / len(c) + t.var(ddof=1) / len(t))
    df = res.df if hasattr(res, "df") else len(c) + len(t) - 2
    tc = stats.t.ppf(1 - alpha / 2, df)
    return TestResult(metric, c.mean(), t.mean(), d, d / c.mean(), d - tc * se, d + tc * se,
                      float(res.pvalue))


def bootstrap_mean_diff_ci(c: np.ndarray, t: np.ndarray, n_boot: int = 2000,
                           alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap CI for mean(t) - mean(c); robust to skewed revenue data."""
    rng = np.random.default_rng(seed)
    c, t = np.asarray(c, float), np.asarray(t, float)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = rng.choice(t, len(t)).mean() - rng.choice(c, len(c)).mean()
    return tuple(np.quantile(diffs, [alpha / 2, 1 - alpha / 2]))


def cuped_adjust(y: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, float, float]:
    """CUPED: y_adj = y - theta * (x - mean(x)), theta = cov(y,x)/var(x).
    Returns adjusted outcome, theta and the variance reduction achieved."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    theta = np.cov(y, x, ddof=1)[0, 1] / x.var(ddof=1)
    y_adj = y - theta * (x - x.mean())
    reduction = 1 - y_adj.var(ddof=1) / y.var(ddof=1)
    return y_adj, float(theta), float(reduction)


def holm_correction(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values (controls family-wise error rate)."""
    p = np.asarray(p_values, float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj.tolist()


def sample_size_per_arm(baseline: float, mde_rel: float, alpha: float = 0.05,
                        power: float = 0.8) -> int:
    """Users per arm needed to detect a relative lift `mde_rel` in a conversion rate."""
    p1, p2 = baseline, baseline * (1 + mde_rel)
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    p_bar = (p1 + p2) / 2
    n = ((za * np.sqrt(2 * p_bar * (1 - p_bar)) + zb * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
         / (p2 - p1) ** 2)
    return int(np.ceil(n))


def minimum_detectable_effect(baseline: float, n_per_arm: int, alpha: float = 0.05,
                              power: float = 0.8) -> float:
    """Approximate relative MDE for a conversion rate given users per arm."""
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    abs_mde = (za + zb) * np.sqrt(2 * baseline * (1 - baseline) / n_per_arm)
    return float(abs_mde / baseline)
