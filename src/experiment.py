"""Simulated A/B test of a pricing rule.

Rule tested: "When a cabin category is at least 70% booked 60 days before sailing,
raise that category's price 5% for the rest of the booking window."

How the simulation works:
- Eligible: departed sailings since 2025 with at least one category >= 70% on the books at day 60.
- Randomization unit: the SAILING. Every eligible category on a sailing gets the same arm, so
  guests on the same sailing never see two prices for the same cabin.
- Control keeps what really happened in the data. Treatment gets prices 5% higher after day 60,
  and late demand responds with a price elasticity drawn per sailing (ASSUMPTION: mean -0.9,
  since guests booking nearly full sailings are not very price sensitive).
- Sold-out categories turned some guests away ("spill"). ASSUMPTION: 0-25% more late demand
  than cabins, so a higher price there loses fewer bookings.
- Main metric: revenue per available cabin (RevPAC) across the eligible categories.
  Guardrail: final occupancy.
- Analysis: Welch t-test, bootstrap 95% CI of the lift, and CUPED, which uses revenue already
  on the books at day 60 (known before the test) to remove differences between sailings.

Because the demand response is simulated, this demonstrates the METHOD. A real lift can only
come from running the test on live sailings.
"""
import json

import numpy as np
import pandas as pd
from scipy import stats

from src import config

PRICE_UP = 0.05
HORIZON = 60           # days before sailing when the rule is checked
THRESHOLD = 0.70       # share of the category's cabins on the books
ELASTICITY_MEAN, ELASTICITY_SD = -0.9, 0.4
SPILL_MAX = 0.25


def eligible_units(rows: pd.DataFrame, as_of=config.AS_OF) -> pd.DataFrame:
    r = rows[(rows["horizon"] == HORIZON) & rows["departed"]
             & (rows["sail_date"] >= "2025-01-01") & (rows["sail_date"] <= as_of)]
    return r[r["otb_pct"] >= THRESHOLD].copy()


def simulate(units: pd.DataFrame, seed=config.SEED) -> pd.DataFrame:
    """Per sailing x category outcomes under control (actual) or treatment (simulated)."""
    rng = np.random.default_rng(seed)
    u = units.copy()
    sailing_ids = u["sailing_id"].unique()
    arm = pd.Series(np.where(rng.random(len(sailing_ids)) < 0.5, "treatment", "control"), index=sailing_ids)
    u["arm"] = u["sailing_id"].map(arm)

    late_cabins = (u["final"] - u["otb"]).clip(lower=0)
    late_rev = (u["final_revenue"] - u["otb_revenue"]).clip(lower=0)
    late_price = (late_rev / late_cabins.where(late_cabins > 0)).fillna(u["avg_price_otb"])
    room = (u["cabins_available"] - u["otb"]).clip(lower=0)

    sold_out = u["final"] >= u["cabins_available"]
    late_demand = late_cabins * np.where(sold_out, 1 + rng.uniform(0, SPILL_MAX, len(u)), 1.0)
    elasticity = u["sailing_id"].map(pd.Series(rng.normal(ELASTICITY_MEAN, ELASTICITY_SD, len(sailing_ids)), index=sailing_ids))
    t_late = np.round(np.minimum(late_demand * (1 + PRICE_UP) ** elasticity, room))

    treat = u["arm"].eq("treatment")
    u["late_cabins"] = np.where(treat, t_late, late_cabins)
    u["late_revenue"] = np.where(treat, t_late * late_price * (1 + PRICE_UP), late_rev)
    u["revenue"] = u["otb_revenue"] + u["late_revenue"]
    u["final_cabins"] = u["otb"] + u["late_cabins"]
    return u


def by_sailing(u: pd.DataFrame) -> pd.DataFrame:
    s = (u.groupby(["sailing_id", "sail_date", "arm"])
         .agg(categories=("cabin_category", "count"), cabins_available=("cabins_available", "sum"),
              otb=("otb", "sum"), otb_revenue=("otb_revenue", "sum"),
              final_cabins=("final_cabins", "sum"), revenue=("revenue", "sum"))
         .reset_index())
    s["revpac"] = s["revenue"] / s["cabins_available"]
    s["pre_revpac"] = s["otb_revenue"] / s["cabins_available"]   # known at day 60, before the test
    s["final_occupancy"] = s["final_cabins"] / s["cabins_available"]
    return s


def bootstrap_lift(c: np.ndarray, t: np.ndarray, n=5000, seed=config.SEED) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    lifts = [(rng.choice(t, len(t)).mean() / rng.choice(c, len(c)).mean() - 1) * 100 for _ in range(n)]
    return float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5))


def analyze(s: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    c, t = s[s["arm"] == "control"], s[s["arm"] == "treatment"]
    lift = (t["revpac"].mean() / c["revpac"].mean() - 1) * 100
    p_raw = stats.ttest_ind(t["revpac"], c["revpac"], equal_var=False).pvalue
    ci_raw = bootstrap_lift(c["revpac"].to_numpy(), t["revpac"].to_numpy())

    # CUPED: subtract the part of RevPAC explained by revenue already on the books at day 60
    theta = np.cov(s["revpac"], s["pre_revpac"])[0, 1] / np.var(s["pre_revpac"], ddof=1)
    s = s.assign(revpac_cuped=s["revpac"] - theta * (s["pre_revpac"] - s["pre_revpac"].mean()))
    c2, t2 = s[s["arm"] == "control"], s[s["arm"] == "treatment"]
    lift_cuped = (t2["revpac_cuped"].mean() / c2["revpac_cuped"].mean() - 1) * 100
    p_cuped = stats.ttest_ind(t2["revpac_cuped"], c2["revpac_cuped"], equal_var=False).pvalue
    ci_cuped = bootstrap_lift(c2["revpac_cuped"].to_numpy(), t2["revpac_cuped"].to_numpy())
    var_cut = (1 - s["revpac_cuped"].var() / s["revpac"].var()) * 100

    # Power analysis (80% power, 5% two-sided): smallest lift this test could reliably detect,
    # and sailings per arm needed to detect a +0.5% lift.
    z = stats.norm.ppf(0.975) + stats.norm.ppf(0.80)
    se = np.sqrt(c2["revpac_cuped"].var() / len(c2) + t2["revpac_cuped"].var() / len(t2))
    mde_pct = z * se / c2["revpac_cuped"].mean() * 100
    pooled_var = (c2["revpac_cuped"].var() + t2["revpac_cuped"].var()) / 2
    n_for_half_pct = int(np.ceil(2 * z ** 2 * pooled_var / (0.005 * c2["revpac_cuped"].mean()) ** 2))

    significant = p_cuped < 0.05
    if significant and lift_cuped > 0:
        decision = "Roll out: significant revenue lift."
    elif significant:
        decision = "Do not roll out: significant revenue loss."
    else:
        decision = ("Inconclusive: no significant lift. Don't roll out broadly. Next, test a larger price "
                    "step only on categories forecast to sell out, where demand exceeds cabins.")

    res = {
        "rule": f"Raise a category's price {PRICE_UP:.0%} when it is >= {THRESHOLD:.0%} booked at {HORIZON} days out",
        "randomization_unit": "sailing",
        "eligible_sailings": len(s), "control_sailings": len(c), "treatment_sailings": len(t),
        "eligible_sailing_categories": int(s["categories"].sum()),
        "control_revpac": round(c["revpac"].mean(), 2), "treatment_revpac": round(t["revpac"].mean(), 2),
        "raw_lift_pct": round(lift, 2), "raw_p_value": round(float(p_raw), 4),
        "raw_ci_95_pct": [round(x, 2) for x in ci_raw],
        "cuped_lift_pct": round(lift_cuped, 2), "cuped_p_value": float(f"{p_cuped:.2g}"),
        "cuped_ci_95_pct": [round(x, 2) for x in ci_cuped],
        "cuped_variance_reduction_pct": round(var_cut, 1),
        "min_detectable_lift_pct": round(mde_pct, 2),
        "sailings_per_arm_to_detect_0.5pct": n_for_half_pct,
        "decision": decision,
        "guardrail_control_occupancy_pct": round(c["final_occupancy"].mean() * 100, 2),
        "guardrail_treatment_occupancy_pct": round(t["final_occupancy"].mean() * 100, 2),
        "assumed_elasticity": f"normal(mean {ELASTICITY_MEAN}, sd {ELASTICITY_SD}) per sailing",
        "assumed_spill": f"sold-out categories had 0-{SPILL_MAX:.0%} more late demand than cabins",
    }
    return res, s


def run(rows: pd.DataFrame, as_of=config.AS_OF) -> dict:
    u = simulate(eligible_units(rows, as_of))
    res, s = analyze(by_sailing(u))
    (config.OUTPUTS / "experiment_results.json").write_text(json.dumps(res, indent=2))
    s.to_csv(config.OUTPUTS / "experiment_sailings.csv", index=False)
    return {"sailings": s, "results": res}


if __name__ == "__main__":
    from src import etl, features
    t = etl.run()["tables"]
    rows = features.build_training_rows(t["bookings"], t["sailings"], t["cabin_inventory"])
    print(json.dumps(run(rows)["results"], indent=2))
