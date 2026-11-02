"""Analyse the checkout-redesign experiment from the warehouse marts and write
reports/results.json and reports/experiment_report.html.

Usage: python analysis/analyze.py
"""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))
import stats as st  # noqa: E402

DB = ROOT / "data" / "warehouse.db"
OUT = ROOT / "reports"
INK, MUTED, C_CTRL, C_TRT = "#1f2933", "#6b7785", "#8a96a3", "#0f6e74"


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)
    ax.yaxis.grid(True, color="#e6e9ec", lw=0.8)
    ax.set_axisbelow(True)


def main() -> None:
    con = sqlite3.connect(DB)
    df = pd.read_sql("select * from fct_experiment_user_outcomes", con)
    seg = pd.read_sql("select * from agg_segment_summary", con)
    con.close()
    c, t = df[df.variant == "control"], df[df.variant == "treatment"]

    res: dict = {"n_control": len(c), "n_treatment": len(t)}
    res["srm_p_value"] = st.srm_check(len(c), len(t))

    conv = st.two_proportion_test(int(c.converted.sum()), len(c), int(t.converted.sum()), len(t))
    rpu = st.welch_test(c.revenue.values, t.revenue.values)
    boot = st.bootstrap_mean_diff_ci(c.revenue.values, t.revenue.values)

    # CUPED on revenue per user, using pre-period revenue as covariate
    y_adj, theta, red = st.cuped_adjust(df.revenue.values, df.pre_revenue.values)
    df["revenue_cuped"] = y_adj
    rpu_cuped = st.welch_test(df.loc[df.variant == "control", "revenue_cuped"].values,
                              df.loc[df.variant == "treatment", "revenue_cuped"].values,
                              metric="revenue_per_user_cuped")

    # Segment (device) conversion tests with Holm correction
    seg_rows = []
    for dev, g in df.groupby("device"):
        gc, gt = g[g.variant == "control"], g[g.variant == "treatment"]
        r = st.two_proportion_test(int(gc.converted.sum()), len(gc),
                                   int(gt.converted.sum()), len(gt), metric=f"conversion_{dev}")
        seg_rows.append({"device": dev, "users": len(g), **r.as_dict()})
    adj = st.holm_correction([r["p_value"] for r in seg_rows])
    for r, a in zip(seg_rows, adj):
        r["p_holm"] = a

    base = c.converted.mean()
    res.update({
        "conversion": conv.as_dict(),
        "revenue_per_user": rpu.as_dict(),
        "revenue_per_user_bootstrap_ci": list(boot),
        "revenue_per_user_cuped": rpu_cuped.as_dict(),
        "cuped_theta": theta,
        "cuped_variance_reduction": red,
        "segments": seg_rows,
        "power": {
            "baseline_conversion": base,
            "mde_rel_at_current_n": st.minimum_detectable_effect(base, len(c)),
            "n_per_arm_for_3pct_lift": st.sample_size_per_arm(base, 0.03),
            "n_per_arm_for_5pct_lift": st.sample_size_per_arm(base, 0.05),
        },
    })
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=float))

    # ---- charts --------------------------------------------------------------
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK})
    fig, ax = plt.subplots(figsize=(6, 3.4))
    devs = [r["device"] for r in seg_rows]
    lifts = [100 * r["rel_lift"] for r in seg_rows]
    lo = [100 * (r["rel_lift"] - r["ci_low"] / r["control"]) for r in seg_rows]
    hi = [100 * (r["ci_high"] / r["control"] - r["rel_lift"]) for r in seg_rows]
    ax.errorbar(lifts, devs, xerr=[lo, hi], fmt="o", color=C_TRT, ecolor=C_CTRL, capsize=3)
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlabel("Relative lift in conversion, % (95% CI)")
    style(ax); ax.xaxis.grid(True, color="#e6e9ec"); ax.yaxis.grid(False)
    ax.set_title("Treatment effect by device", loc="left", color=INK)
    seg_png = fig_to_b64(fig)

    fig, ax = plt.subplots(figsize=(6, 3.4))
    pv = seg.pivot(index="device", columns="variant", values="conversion_rate") * 100
    x = np.arange(len(pv))
    ax.bar(x - 0.2, pv["control"], 0.4, color=C_CTRL, label="Control")
    ax.bar(x + 0.2, pv["treatment"], 0.4, color=C_TRT, label="Treatment")
    ax.set_xticks(x, pv.index)
    ax.set_ylabel("Conversion rate, %")
    ax.legend(frameon=False)
    style(ax)
    ax.set_title("Conversion rate by device and variant", loc="left", color=INK)
    conv_png = fig_to_b64(fig)

    def pct(v, d=2):
        return f"{100 * v:.{d}f}%"

    tiles = [
        ("Users in test", f"{len(df):,}"),
        ("SRM p-value", f"{res['srm_p_value']:.2f}"),
        ("Conversion lift", f"{pct(conv.rel_lift, 1)}  (p={conv.p_value:.3f})"),
        ("Revenue/user lift", f"{pct(rpu.rel_lift, 1)}  (p={rpu.p_value:.3f})"),
        ("CUPED variance cut", pct(red, 1)),
        ("Revenue/user lift, CUPED", f"{pct(rpu_cuped.abs_diff / rpu.control, 1)}  (p={rpu_cuped.p_value:.3f})"),
    ]
    seg_table = "".join(
        f"<tr><td>{r['device']}</td><td>{r['users']:,}</td><td>{pct(r['control'])}</td>"
        f"<td>{pct(r['treatment'])}</td><td>{pct(r['rel_lift'], 1)}</td>"
        f"<td>{r['p_value']:.4f}</td><td>{r['p_holm']:.4f}</td></tr>" for r in seg_rows)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Checkout Redesign Experiment</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:{INK};background:#fafbfc;margin:0;padding:24px;max-width:1000px;margin:auto}}
h1{{font-size:22px;margin:0 0 4px}} p.sub{{color:{MUTED};margin:0 0 20px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}}
.tile{{background:#fff;border:1px solid #e6e9ec;border-radius:8px;padding:12px}}
.tile .k{{color:{MUTED};font-size:12px}} .tile .v{{font-size:18px;font-weight:600;margin-top:4px}}
.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}
img{{width:100%;background:#fff;border:1px solid #e6e9ec;border-radius:8px}}
table{{border-collapse:collapse;width:100%;background:#fff;margin-top:16px;font-size:14px}}
th,td{{border-bottom:1px solid #e6e9ec;padding:6px 8px;text-align:right}} th:first-child,td:first-child{{text-align:left}}
</style></head><body>
<h1>Checkout redesign v2: experiment readout</h1>
<p class="sub">Simulated data. 50/50 user-level randomisation, outcomes measured after assignment.</p>
<div class="tiles">{''.join(f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in tiles)}</div>
<div class="charts"><img alt="Conversion by device" src="data:image/png;base64,{conv_png}">
<img alt="Lift by device" src="data:image/png;base64,{seg_png}"></div>
<table><tr><th>Device</th><th>Users</th><th>Control CR</th><th>Treatment CR</th><th>Lift</th><th>p</th><th>p (Holm)</th></tr>{seg_table}</table>
<p class="sub" style="margin-top:16px">Power: baseline conversion {pct(base)}; with {len(c):,} users per arm the
minimum detectable relative lift is about {pct(res['power']['mde_rel_at_current_n'], 1)} (80% power, alpha 0.05).</p>
</body></html>"""
    (OUT / "experiment_report.html").write_text(html)
    print(json.dumps({k: res[k] for k in ("n_control", "n_treatment", "srm_p_value")}, indent=1))
    print("conversion", {k: round(v, 5) if isinstance(v, float) else v for k, v in conv.as_dict().items()})
    print("rpu", {k: round(v, 5) if isinstance(v, float) else v for k, v in rpu.as_dict().items()})
    print("rpu_cuped", {k: round(v, 5) if isinstance(v, float) else v for k, v in rpu_cuped.as_dict().items()})
    print("bootstrap", boot, "cuped_reduction", round(red, 4))
    for r in seg_rows:
        print(r["device"], round(r["rel_lift"], 4), round(r["p_value"], 5), round(r["p_holm"], 5))
    print("power", res["power"])


if __name__ == "__main__":
    main()
