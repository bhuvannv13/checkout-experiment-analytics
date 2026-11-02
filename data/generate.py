"""Generate a simulated e-commerce dataset for a checkout-redesign A/B test.

The data is synthetic (no real customers). It is built to look like raw product
analytics exports, including the usual problems an analyst has to clean:
duplicate events, missing device values, inconsistent country codes, test
accounts and a handful of orders with zero or negative value.

Output: data/raw/*.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
N_USERS = 200_000
START = pd.Timestamp("2026-03-02")
PRE_DAYS = 28          # pre-experiment period (used for CUPED)
EXP_DAYS = 21          # experiment period

OUT = Path(__file__).parent / "raw"


def main() -> None:
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- users -------------------------------------------------------------
    user_id = np.arange(1, N_USERS + 1)
    device = rng.choice(["mobile", "desktop", "tablet"], N_USERS, p=[0.58, 0.36, 0.06])
    country = rng.choice(["IE", "GB", "DE", "FR", "ES", "NL"], N_USERS,
                         p=[0.30, 0.25, 0.15, 0.12, 0.10, 0.08])
    signup = START - pd.to_timedelta(rng.integers(30, 720, N_USERS), unit="D")
    is_test = rng.random(N_USERS) < 0.004            # internal / QA accounts
    engagement = rng.gamma(0.35, 1.0, N_USERS)        # latent propensity to buy

    users = pd.DataFrame({
        "user_id": user_id,
        "signup_date": signup.date,
        "device": device,
        "country": country,
        "is_internal": is_test.astype(int),
    })
    # messy raw values
    m = rng.random(N_USERS)
    users.loc[m < 0.02, "device"] = None
    users.loc[(m >= 0.02) & (m < 0.05), "country"] = users["country"].str.lower()
    users.loc[(m >= 0.05) & (m < 0.06), "country"] = " " + users["country"] + " "

    # ---- assignment (50/50) ------------------------------------------------
    variant = np.where(rng.random(N_USERS) < 0.5, "control", "treatment")
    assign_day = rng.integers(0, EXP_DAYS, N_USERS)
    exp_start = START + pd.Timedelta(days=PRE_DAYS)
    assignments = pd.DataFrame({
        "user_id": user_id,
        "experiment_id": "checkout_redesign_v2",
        "variant": variant,
        "assigned_at": (exp_start + pd.to_timedelta(assign_day, unit="D")
                        + pd.to_timedelta(rng.integers(0, 86_400, N_USERS), unit="s")),
    })

    # ---- orders ------------------------------------------------------------
    base_rate = 0.045 * engagement / engagement.mean()
    device_mult = pd.Series(device).map({"mobile": 0.85, "desktop": 1.25, "tablet": 1.0}).to_numpy()
    aov = pd.Series(country).map({"IE": 62, "GB": 58, "DE": 66, "FR": 55, "ES": 49, "NL": 64}).to_numpy()

    rows = []
    # pre-period orders (for CUPED covariate)
    pre_n = rng.poisson(base_rate * device_mult * 1.6)
    for uid, n in zip(user_id[pre_n > 0], pre_n[pre_n > 0]):
        for _ in range(n):
            ts = START + pd.Timedelta(seconds=int(rng.integers(0, PRE_DAYS * 86_400)))
            rows.append((uid, ts, rng.lognormal(np.log(aov[uid - 1]), 0.45)))

    # experiment-period orders: treatment lifts conversion mainly on mobile
    lift = np.where(variant == "treatment",
                    np.where(device == "mobile", 1.09, 1.02), 1.0)
    exp_rate = base_rate * device_mult * lift
    exp_n = rng.poisson(exp_rate)
    for uid, n in zip(user_id[exp_n > 0], exp_n[exp_n > 0]):
        a = assignments.at[uid - 1, "assigned_at"]
        for _ in range(n):
            ts = a + pd.Timedelta(seconds=int(rng.integers(60, (EXP_DAYS - 1) * 86_400)))
            rows.append((uid, ts, rng.lognormal(np.log(aov[uid - 1]), 0.45)))

    orders = pd.DataFrame(rows, columns=["user_id", "ordered_at", "order_value"])
    orders = orders.sort_values("ordered_at").reset_index(drop=True)
    orders.insert(0, "order_id", np.arange(100_001, 100_001 + len(orders)))
    orders["order_value"] = orders["order_value"].round(2)
    orders["currency"] = "EUR"
    # messy: zero/negative values (refund artefacts) and duplicated rows
    bad = rng.choice(len(orders), 25, replace=False)
    orders.loc[bad[:15], "order_value"] = 0.0
    orders.loc[bad[15:], "order_value"] *= -1
    dups = orders.sample(120, random_state=SEED)
    orders = pd.concat([orders, dups]).sort_values("ordered_at")

    # ---- checkout events (funnel) -------------------------------------------
    started = rng.random(N_USERS) < np.clip(exp_rate * 6, 0, 0.9)
    started |= exp_n > 0
    ev = assignments.loc[started, ["user_id", "assigned_at"]].copy()
    ev["event_name"] = "checkout_started"
    ev["event_ts"] = ev["assigned_at"] + pd.to_timedelta(rng.integers(30, 3_000, len(ev)), unit="s")
    events = ev[["user_id", "event_name", "event_ts"]]
    events = pd.concat([events, events.sample(300, random_state=1)])  # duplicate fires

    users.to_csv(OUT / "users.csv", index=False)
    assignments.to_csv(OUT / "assignments.csv", index=False)
    orders.to_csv(OUT / "orders.csv", index=False)
    events.to_csv(OUT / "checkout_events.csv", index=False)
    print(f"users={len(users):,} orders={len(orders):,} events={len(events):,}")


if __name__ == "__main__":
    main()
