"""Charts for the README and for presenting results."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import config  # noqa: E402

BLUE, GRAY, ORANGE = "#1f4e79", "#a6a6a6", "#c55a11"
plt.rcParams.update({"figure.dpi": 120, "axes.spines.top": False, "axes.spines.right": False,
                     "font.size": 10, "axes.titleweight": "bold"})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(config.FIGURES / name)
    plt.close(fig)


def error_by_horizon():
    bt = json.loads((config.OUTPUTS / "forecast_backtest.json").read_text())
    d = pd.DataFrame(bt["by_horizon"])
    x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.bar(x - 0.2, d["baseline_mape"], 0.4, color=GRAY, label="Baseline: last year's pace")
    ax.bar(x + 0.2, d["model_mape"], 0.4, color=BLUE, label="XGBoost model")
    ax.set_xticks(x, [f"{h}d" for h in d["horizon"]])
    ax.set_xlabel("Days before sailing when the forecast is made")
    ax.set_ylabel("MAPE (%)")
    ax.set_title("Forecast error: model vs baseline (backtest)")
    ax.legend(frameon=False)
    save(fig, "error_by_horizon.png")


def backtest_scatter():
    p = pd.read_csv(config.OUTPUTS / "backtest_predictions.csv")
    p = p[p["horizon"] == 60]
    fig, ax = plt.subplots(figsize=(5, 4.6))
    ax.scatter(p["final"], p["pred_baseline"], s=8, alpha=0.4, color=GRAY, label="Baseline")
    ax.scatter(p["final"], p["pred_model"], s=8, alpha=0.5, color=BLUE, label="XGBoost")
    lim = [0, p["final"].max() * 1.05]
    ax.plot(lim, lim, color="black", lw=1)
    ax.set_xlabel("Actual final cabins")
    ax.set_ylabel("Forecast made 60 days out")
    ax.set_title("Forecast vs actual, 60 days out")
    ax.legend(frameon=False)
    save(fig, "backtest_scatter_60d.png")


def feature_importance():
    f = pd.read_csv(config.OUTPUTS / "feature_importance.csv").sort_values("importance")
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.barh(f["feature"], f["importance"], color=BLUE)
    ax.set_title("What drives the forecast (XGBoost importance)")
    save(fig, "feature_importance.png")


def occupancy_by_month(tables):
    b, s, inv = tables["bookings"], tables["sailings"], tables["cabin_inventory"]
    dep = s[s["sail_date"] <= config.AS_OF]
    conf = b[b["status"] == "confirmed"].groupby("sailing_id").size()
    cap = inv.groupby("sailing_id")["cabins_available"].sum()
    occ = (conf / cap).reindex(dep["sailing_id"]).fillna(0)
    m = pd.Series(occ.to_numpy(), index=dep["sail_date"].dt.month.to_numpy()).groupby(level=0).mean() * 100
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(m.index, m.values, color=[ORANGE if v < 80 else BLUE for v in m.values])
    ax.set_xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_ylim(50, 100)
    ax.set_ylabel("Average occupancy (%)")
    ax.set_title("Seasonality: occupancy by sailing month")
    save(fig, "occupancy_by_month.png")


def pace_example(tables):
    pc = pd.read_csv(config.POWERBI / "pace_curves.csv")
    fc = pd.read_csv(config.OUTPUTS / "forecast_open_sailings.csv")
    s = tables["sailings"]
    # The sailing 6-13 weeks out that is furthest behind last year's pace
    sail = (fc.groupby("sailing_id").agg(otb=("otb", "sum"), ly=("ly_otb", "sum"), days=("days_to_sailing", "first"))
            .query("ly > 50 and 42 <= days <= 90").assign(pace=lambda d: d.otb / d.ly).sort_values("pace").index[0])
    sd = s.set_index("sailing_id").loc[sail, "sail_date"]
    ship = s.set_index("sailing_id").loc[sail, "ship_id"]
    nights = s.set_index("sailing_id").loc[sail, "nights"]
    ly = s[(s.ship_id == ship) & (s.nights == nights) & ((s.sail_date - (sd - pd.Timedelta(days=364))).abs() <= pd.Timedelta(days=4))]
    fig, ax = plt.subplots(figsize=(7, 3.8))
    if len(ly):
        c = pc[pc.sailing_id == ly.sailing_id.iloc[0]]
        ax.plot(c["weeks_out"], c["cumulative_occupancy"] * 100, color=GRAY, label=f"Last year ({ly.sail_date.iloc[0].date()})")
    weeks_now = (sd - config.AS_OF).days // 7
    c = pc[(pc.sailing_id == sail) & (pc.weeks_out >= weeks_now)]
    ax.plot(c["weeks_out"], c["cumulative_occupancy"] * 100, color=BLUE, lw=2, label=f"This year ({sd.date()}), so far")
    ax.invert_xaxis()
    ax.set_xlabel("Weeks before sailing")
    ax.set_ylabel("Cabins booked (%)")
    ax.set_title(f"Booking pace: sailing {sail} vs same sailing last year")
    ax.legend(frameon=False)
    save(fig, "pace_example.png")


def experiment_chart():
    r = json.loads((config.OUTPUTS / "experiment_results.json").read_text())
    fig, ax = plt.subplots(figsize=(6.5, 2.6))
    for i, (label, lift, ci) in enumerate([("Raw", r["raw_lift_pct"], r["raw_ci_95_pct"]),
                                           ("CUPED", r["cuped_lift_pct"], r["cuped_ci_95_pct"])]):
        ax.errorbar(lift, i, xerr=[[lift - ci[0]], [ci[1] - lift]], fmt="o", color=BLUE, capsize=5)
    ax.axvline(0, color="black", lw=1)
    ax.set_yticks([0, 1], ["Raw", "CUPED"])
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlabel("Revenue per available cabin lift (%), 95% CI")
    ax.set_title("Pricing A/B test: +5% price at >= 70% booked, 60 days out")
    save(fig, "experiment_lift.png")


def run(tables):
    error_by_horizon()
    backtest_scatter()
    feature_importance()
    occupancy_by_month(tables)
    pace_example(tables)
    experiment_chart()
