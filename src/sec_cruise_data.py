"""Real cruise-line operating data from SEC filings (Royal Caribbean, Carnival, Norwegian).

Cruise lines don't publish booking-level data, but every 10-Q and 10-K reports operating
statistics in its MD&A tables:
- passengers carried
- passenger cruise days (PCD)
- capacity (APCD for Royal Caribbean, ALBDs for Carnival, Capacity Days for Norwegian)
- occupancy % (PCD / capacity, industry practice: 2 guests per cabin, so it can exceed 100%)

How quarters are built:
- Q1-Q3 come straight from each 10-Q (the "three months ended" column).
- Q4 is derived as the full year (10-K) minus the first nine months (Q3 10-Q), for PCD and
  capacity, and occupancy is recomputed from those.
- Total revenue (tickets + onboard) comes from the SEC XBRL API; the tag changed in 2018, so several are combined.

Run:  python -m src.sec_cruise_data   (downloads to data/sec/, writes outputs/sec_cruise_quarterly.csv)
The SEC asks automated clients to identify themselves; set SEC_USER_AGENT to "Your Name you@example.com".
"""
import html
import json
import os
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

from src import config

UA = os.environ.get("SEC_USER_AGENT", "cruise-pricing-forecast research admin@example.org")
CACHE = config.ROOT / "data" / "sec"
CACHE.mkdir(parents=True, exist_ok=True)
START_YEAR = 2016

COMPANIES = {
    "Royal Caribbean": {"cik": "0000884887", "capacity": r"APCD", "scale": 1},
    "Carnival": {"cik": "0000815097", "capacity": r"Available Lower Berth Days", "scale": 1_000_000},
    "Norwegian": {"cik": "0001513761", "capacity": r"Capacity Days", "scale": 1},
}
NUM = r"\(?-?[\d,]+(?:\.\d+)?\)?"


def get(url: str, cache_name: str) -> str:
    path = CACHE / cache_name
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())
        time.sleep(0.2)  # stay well under the SEC's 10 requests/second limit
    return path.read_text(encoding="utf-8", errors="ignore")


def text_of(raw_html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", raw_html)
    t = html.unescape(t).replace("​", " ")
    return re.sub(r"\s+", " ", t)


def row_numbers(t: str, label: str, min_count: int = 2) -> list[float] | None:
    """First table row starting with `label` that is followed by numbers (skips definitions).

    Values are scaled when the row label says "(in thousands)" or "(in millions)".
    """
    pattern = label + r"([^0-9%]{0,80}?)((?:" + NUM + r"\s*%?\s*){" + str(min_count) + r",})"
    for m in re.finditer(pattern, t):
        between = m.group(1).lower()
        scale = 1_000_000 if "million" in between else 1_000 if "thousand" in between else 1
        out = []
        for v in re.findall(NUM, m.group(2)):
            v = v.replace(",", "").strip("()")
            try:
                out.append(float(v))
            except ValueError:
                pass
        # Skip years mistaken for values
        out = [v for v in out if not (1990 <= v <= 2100)]
        if len(out) >= min_count:
            return [v * scale for v in out]
    return None


def parse_filing(t: str, cfg: dict) -> dict | None:
    pcd = row_numbers(t, r"Passenger Cruise Days")
    cap = row_numbers(t, cfg["capacity"])
    occ = row_numbers(t, r"Occupancy(?: percentage| Percentage)?(?: \([a-z]\))?")
    pax = row_numbers(t, r"Passengers [Cc]arried")
    if not (cap and occ):
        return None
    if not pcd:  # older Carnival filings report occupancy and capacity but not PCDs
        pcd = [c * o / 100 for c, o in zip(cap, occ)]
    return {"pcd": pcd, "capacity": cap, "occupancy_pct": occ, "passengers": pax}


def filings(cik: str) -> list[dict]:
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json"))
    r = sub["filings"]["recent"]
    out = []
    for i, form in enumerate(r["form"]):
        if form in ("10-Q", "10-K") and r["reportDate"][i] and int(r["reportDate"][i][:4]) >= START_YEAR:
            out.append({"form": form, "period_end": r["reportDate"][i], "acc": r["accessionNumber"][i],
                        "doc": r["primaryDocument"][i]})
    return out


def operating_stats(name: str, cfg: dict) -> pd.DataFrame:
    cik_int = str(int(cfg["cik"]))
    rows = []
    for f in filings(cfg["cik"]):
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{f['acc'].replace('-', '')}/{f['doc']}"
        parsed = parse_filing(text_of(get(url, f"{cfg['cik']}_{f['acc']}.htm")), cfg)
        if parsed is None:
            continue
        rows.append({"company": name, "form": f["form"], "period_end": f["period_end"], **parsed})
    q = []
    by_end = {r["period_end"]: r for r in rows}
    for r in rows:
        end = pd.Timestamp(r["period_end"])
        if r["form"] == "10-Q":
            q.append({"company": name, "quarter_end": end, "source": "10-Q",
                      "passengers": r["passengers"][0] if r["passengers"] else None,
                      "pcd": r["pcd"][0], "capacity_days": r["capacity"][0], "occupancy_pct": r["occupancy_pct"][0]})
        else:
            # Q4 = full year minus the nine-month column of the Q3 10-Q (about 3 months earlier)
            q3_end = [k for k in by_end if by_end[k]["form"] == "10-Q"
                      and 80 <= (end - pd.Timestamp(k)).days <= 100]
            if not q3_end:
                continue
            q3 = by_end[q3_end[0]]
            if len(q3["pcd"]) < 3 or len(q3["capacity"]) < 3:
                continue
            pcd = r["pcd"][0] - q3["pcd"][2]
            cap = r["capacity"][0] - q3["capacity"][2]
            pax = (r["passengers"][0] - q3["passengers"][2]) if r["passengers"] and q3["passengers"] and len(q3["passengers"]) >= 3 else None
            if cap > 0:
                q.append({"company": name, "quarter_end": end, "source": "10-K minus Q3 YTD",
                          "passengers": pax, "pcd": pcd, "capacity_days": cap,
                          "occupancy_pct": round(pcd / cap * 100, 1)})
    return pd.DataFrame(q)


REVENUE_CONCEPTS = ["RevenueFromContractWithCustomerExcludingAssessedTax",
                    "RevenueFromContractWithCustomerIncludingAssessedTax", "Revenues"]


def total_revenue(name: str, cfg: dict) -> pd.DataFrame:
    """Total revenue (tickets + onboard), quarterly. The XBRL tag changed after 2018, so several are combined."""
    facts = json.loads(get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cfg['cik']}.json", f"facts_{cfg['cik']}.json"))
    usgaap = facts["facts"]["us-gaap"]
    vals = []
    for rank, concept in enumerate(REVENUE_CONCEPTS):
        for v in usgaap.get(concept, {}).get("units", {}).get("USD", []):
            if "start" in v:
                vals.append({**v, "rank": rank})
    df = pd.DataFrame(vals)
    if df.empty:
        return df
    df = df.sort_values(["rank", "filed"], ascending=[True, False]).drop_duplicates(["start", "end"])
    df["start"], df["end"] = pd.to_datetime(df["start"]), pd.to_datetime(df["end"])
    df["days"] = (df["end"] - df["start"]).dt.days
    qtr = df[df["days"].between(80, 100)][["end", "val"]].rename(columns={"val": "total_revenue"})
    annual = df[df["days"].between(350, 380)]
    extra = []
    for a in annual.itertuples():
        if (qtr["end"] == a.end).any():
            continue
        inside = qtr[(qtr["end"] > a.start) & (qtr["end"] < a.end)]
        if len(inside) == 3:  # Q4 = full year minus Q1-Q3
            extra.append({"end": a.end, "total_revenue": a.val - inside["total_revenue"].sum()})
    qtr = pd.concat([qtr, pd.DataFrame(extra)], ignore_index=True)
    return qtr.rename(columns={"end": "quarter_end"}).assign(company=name)


def run() -> pd.DataFrame:
    frames = []
    for name, cfg in COMPANIES.items():
        ops = operating_stats(name, cfg)
        rev = total_revenue(name, cfg)
        if not rev.empty:
            ops = ops.merge(rev, on=["company", "quarter_end"], how="left")
        frames.append(ops)
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["company", "quarter_end"]).sort_values(["company", "quarter_end"])
    # Quality check: reported occupancy must equal PCD / capacity (within 2 points), or the row was misread
    consistent = (df["pcd"] / df["capacity_days"] * 100 - df["occupancy_pct"]).abs() <= 2
    dropped = df[~consistent]
    if len(dropped):
        print(f"Dropped {len(dropped)} inconsistent row(s):", dropped[["company", "quarter_end"]].to_dict("records"))
    df = df[consistent].copy()
    df["revenue_per_pcd"] = (df["total_revenue"] / df["pcd"]).round(2)
    df["calendar_quarter"] = "Q" + df["quarter_end"].dt.quarter.astype(str)
    df["year"] = df["quarter_end"].dt.year
    # Mar 2020 - Dec 2022: sailings suspended, then a ramp-up at reduced occupancy (COVID-19).
    # Those quarters aren't comparable to normal operations, so they're flagged and left out of averages.
    df["covid_period"] = df["quarter_end"].between("2020-03-01", "2022-12-31")
    df.to_csv(config.OUTPUTS / "sec_cruise_quarterly.csv", index=False, date_format="%Y-%m-%d")
    return df


if __name__ == "__main__":
    d = run()
    print(d.groupby("company").size().to_string())
    print(d[~d["covid_period"]].groupby(["company", "calendar_quarter"])["occupancy_pct"].mean().round(1).unstack().to_string())
    print(d.tail(12).to_string())
