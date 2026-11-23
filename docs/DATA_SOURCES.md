# Data Sources & Methodology

This project uses **two layers of data**:

1. **Real, public data:** ten years of quarterly operating results for the three largest publicly traded cruise companies, taken from their SEC filings, plus U.S. economic indicators from the Bureau of Labor Statistics and the University of Michigan.
2. **Synthetic booking-level data:** about 510,000 bookings. No cruise line publishes individual bookings, so the project generates them and **calibrates them to the real data** above.

The real data is used to **calibrate** the synthetic bookings, to **benchmark** them, and to train and test a **real-data forecast** of each company's revenue per passenger day.

> All data is public. The project isn't affiliated with or endorsed by any company named here.
>
> **Every number can be traced to its source.** Each source below is linked, [§10](#10-references) has formal citations, and **[SEC_FILINGS.md](SEC_FILINGS.md) lists all 102 SEC filings used, each with a direct link to the document on EDGAR.** Data was retrieved in November 2026.

---

## 1. Companies

| Company | Ticker | SEC CIK | Main brands | Fiscal year ends | Capacity metric in filings | Quarters collected | Filings on EDGAR |
|---|---|---|---|---|---|---|---|
| **Royal Caribbean Cruises Ltd.** (Royal Caribbean Group) | RCL | [0000884887](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000884887&type=10-&dateb=&owner=include&count=40) | Royal Caribbean International, Celebrity Cruises, Silversea | Dec 31 | APCD (available passenger cruise days) | **39** (Q1 2017 – Q3 2026) | [30 10-Qs + 9 10-Ks](SEC_FILINGS.md#royal-caribbean-cruises-ltd-cik-0000884887) |
| **Norwegian Cruise Line Holdings Ltd.** | NCLH | [0001513761](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001513761&type=10-&dateb=&owner=include&count=40) | Norwegian Cruise Line, Oceania Cruises, Regent Seven Seas | Dec 31 | Capacity Days | **34** (Q1 2016 – Q3 2026) | [28 10-Qs + 6 10-Ks](SEC_FILINGS.md#norwegian-cruise-line-holdings-ltd-cik-0001513761) |
| **Carnival Corporation & plc** | CCL | [0000815097](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000815097&type=10-&dateb=&owner=include&count=40) | Carnival Cruise Line, Princess, Holland America, AIDA, Costa, P&O, Cunard, Seabourn | Nov 30 | ALBDs (available lower berth days) | **29** (Aug 2016 – Aug 2026) | [26 10-Qs + 3 10-Ks](SEC_FILINGS.md#carnival-corporation--plc-cik-0000815097) |

**Total: 102 company-quarters**, taken from **102 SEC filings** (84 10-Qs and 18 10-Ks; [full list with links](SEC_FILINGS.md)). About 130 filings were downloaded; the rest were older or didn't report the statistics in a usable table. Of these, **83** are normal-operations quarters. The 19 quarters from March 2020 to December 2022 are flagged as COVID-19, when sailings were suspended and then ramped back up.

---

## 2. Sources

| # | Source | What it provides | Where to see it | How the code reads it | Coverage |
|---|---|---|---|---|---|
| 1 | **SEC EDGAR: filing index** ([about the API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)) | The list of each company's 10-Q and 10-K filings (accession number, period, document name) | [Royal Caribbean](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000884887&type=10-&dateb=&owner=include&count=40) · [Norwegian](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001513761&type=10-&dateb=&owner=include&count=40) · [Carnival](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000815097&type=10-&dateb=&owner=include&count=40) | [CIK0000884887.json](https://data.sec.gov/submissions/CIK0000884887.json) · [CIK0001513761.json](https://data.sec.gov/submissions/CIK0001513761.json) · [CIK0000815097.json](https://data.sec.gov/submissions/CIK0000815097.json) | 2016 – Nov 2026 |
| 2 | **SEC EDGAR: filing documents** | Operating statistics tables in each quarterly (10-Q) and annual (10-K) report: passengers carried, passenger cruise days, capacity, occupancy | **[SEC_FILINGS.md](SEC_FILINGS.md): every filing used, with a direct link** | `https://www.sec.gov/Archives/edgar/data/{CIK}/{accession}/{document}.htm` | 102 filings |
| 3 | **SEC XBRL "company facts" API** | Total revenue per quarter, as tagged in the financial statements | Revenue in each filing's income statement | [Royal Caribbean](https://data.sec.gov/api/xbrl/companyfacts/CIK0000884887.json) · [Norwegian](https://data.sec.gov/api/xbrl/companyfacts/CIK0001513761.json) · [Carnival](https://data.sec.gov/api/xbrl/companyfacts/CIK0000815097.json) | 2016 – Q3 2026 |
| 4 | **U.S. Bureau of Labor Statistics (BLS)** ([Public API](https://www.bls.gov/developers/)) | CPI for **airline fares**, U.S. city average, seasonally adjusted (series `CUSR0000SETG01`) and the **unemployment rate** (`LNS14000000`) | [CUSR0000SETG01](https://data.bls.gov/timeseries/CUSR0000SETG01) · [LNS14000000](https://data.bls.gov/timeseries/LNS14000000) | `https://api.bls.gov/publicAPI/v1/timeseries/data/` | Jan 2015 – Oct 2026 (monthly) |
| 5 | **University of Michigan, Surveys of Consumers** | **Index of Consumer Sentiment** (ICS) | [Surveys of Consumers](https://www.sca.isr.umich.edu/) · [data tables](https://www.sca.isr.umich.edu/tables.html) | [tbmics.csv](https://www.sca.isr.umich.edu/files/tbmics.csv) | Jan 2014 – Nov 2026 used (monthly) |

**Notes:**
- The SEC asks automated tools to identify themselves ([SEC fair access policy](https://www.sec.gov/os/accessing-edgar-data)). The script sends a descriptive User-Agent, which you can set with `SEC_USER_AGENT`, and waits between requests to stay well under the SEC's 10-requests-per-second limit.
- BLS didn't publish one month (October 2025, during the federal government shutdown). The script skips that month instead of inventing a value.
- FRED (St. Louis Fed) carries the same economic series, but its download endpoint times out for scripts, so the original BLS and Michigan sources are used directly.

---

## 3. Fields and definitions

| Field | Meaning | Where it comes from |
|---|---|---|
| `passengers` | Passengers carried in the quarter | 10-Q / 10-K operating statistics |
| `pcd` | **Passenger cruise days**: passengers × days on board | 10-Q / 10-K operating statistics |
| `capacity_days` | **Capacity**: 2 guests per cabin × cabins × days available for sale (APCD / ALBDs / Capacity Days) | 10-Q / 10-K operating statistics |
| `occupancy_pct` | **Occupancy (load factor)** = PCD ÷ capacity. **Above 100%** means some cabins held 3–4 guests | 10-Q / 10-K, and re-checked against PCD ÷ capacity |
| `total_revenue` | Total revenue: tickets plus onboard spending | XBRL company facts |
| `revenue_per_pcd` | **Revenue per passenger cruise day** = total revenue ÷ PCD. A yield-style metric: how much revenue each guest-day brings in | Calculated |
| `covid_period` | True for Mar 2020 – Dec 2022 | Calculated |
| `source` | `10-Q`, or `10-K minus Q3 YTD` for derived fourth quarters | Calculated |

---

## 4. How the dataset is built (`src/sec_cruise_data.py`)

1. **List the filings.** For each company, read the EDGAR filing index and keep every 10-Q and 10-K with a period from 2016 on.
2. **Download each report** and convert its HTML to plain text. Files are cached in `data/sec/`, about 250 MB for 130 filings.
3. **Find the operating statistics rows.** In each report, find the table rows that start with "Passengers carried", "Passenger Cruise Days", the company's capacity label (APCD / ALBDs / Capacity Days) and "Occupancy", and read the numbers that follow. Definitions and footnotes that mention the same words are skipped.
4. **Handle units.** Royal Caribbean and Norwegian report exact counts. Carnival reports in **millions** in recent years and **thousands** in older years. The script reads the "(in millions)" or "(in thousands)" label on each row and scales the numbers.
5. **Handle older Carnival reports.** Filings before 2022 report occupancy and capacity but not passenger cruise days. For those, PCD is calculated as occupancy × capacity.
6. **Build the fourth quarter.** Annual reports only give full-year totals. Q4 = full year (10-K) − first nine months (the year-to-date column of the Q3 10-Q), for PCD, capacity and passengers. Occupancy is then recalculated from those. This produced 18 fourth quarters.
7. **Add revenue.** Quarterly revenue comes from the XBRL API. The XBRL tag changed in 2018 when revenue-recognition rules changed, so three tags are combined in priority order: `RevenueFromContractWithCustomerExcludingAssessedTax`, `RevenueFromContractWithCustomerIncludingAssessedTax`, then `Revenues`. Q4 revenue = full year − Q1 – Q3.
8. **Check quality.** A quarter is **dropped** if its reported occupancy doesn't equal PCD ÷ capacity within 2 points. That would mean a table was misread. **One row was caught and dropped:** Norwegian Q3 2022, where a footnote marker was read as the capacity.
9. **Flag COVID-19 quarters** (Mar 2020 – Dec 2022), so they're excluded from averages and models.
10. **Save** to `outputs/sec_cruise_quarterly.csv`: 102 rows, one per company per quarter.

---

## 5. What the data looks like

**The latest quarter for each company:**

| Company | Quarter ending | Passengers | Passenger cruise days | Capacity days | Occupancy | Total revenue | Revenue per PCD | Source filing |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Royal Caribbean | Sep 30, 2026 | 2,676,480 | 16,692,392 | 14,844,688 | **112.4%** | $5.59 B | **$334.94** | [10-Q, filed Oct 27, 2026](https://www.sec.gov/Archives/edgar/data/884887/000088488726000044/rcl-20260930.htm) |
| Norwegian | Sep 30, 2026 | 983,214 | 7,204,938 | 6,766,454 | **106.5%** | $2.95 B | **$408.99** | [10-Q, filed Oct 29, 2026](https://www.sec.gov/Archives/edgar/data/1513761/000110465926120217/nclh-20260930x10q.htm) |
| Carnival | Aug 31, 2026 | 3.9 M | 27.9 M | 24.9 M | **111.8%** | $8.44 B | **$302.33** | [10-Q, filed Sep 29, 2026](https://www.sec.gov/Archives/edgar/data/815097/000081509726000107/ccl-20260831.htm) |

**Royal Caribbean, 2019, before COVID-19:**

| Quarter | Source | Occupancy | Total revenue | Revenue per PCD | Source filing |
|---|---|---:|---:|---:|---|
| Q1 2019 | 10-Q | 107.1% | $2.44 B | $231.00 | [10-Q, filed May 2, 2019](https://www.sec.gov/Archives/edgar/data/884887/000088488719000023/final2019q110q.htm) |
| Q2 2019 | 10-Q | 108.5% | $2.81 B | $247.90 | [10-Q, filed Jul 26, 2019](https://www.sec.gov/Archives/edgar/data/884887/000088488719000042/a2019q210q.htm) |
| Q3 2019 | 10-Q | 110.5% | $3.19 B | $268.63 | [10-Q, filed Oct 30, 2019](https://www.sec.gov/Archives/edgar/data/884887/000088488719000046/a2019q310q.htm) |
| Q4 2019 | 10-K − Q3 YTD | 106.3% | $2.52 B | $227.67 | [10-K, filed Feb 25, 2020](https://www.sec.gov/Archives/edgar/data/884887/000088488720000009/rcl-20191231.htm) minus the Q3 10-Q above |

To check a number yourself: open the filing and search for "Passenger Cruise Days" or "Occupancy". The operating statistics table is in Management's Discussion and Analysis.

---

## 6. What the real data shows

**Ships sail more than full in every quarter.** Average occupancy outside COVID-19 is about **102–112%**. Q3, with summer family travel, is the peak, and Q1/Q4 are the lows.

**Growth since 2019 came from price, not from filling more cabins:**

| Company | Occupancy, 2019 avg → last 4 quarters | Revenue per PCD, 2019 avg → last 4 quarters |
|---|---|---|
| **Royal Caribbean** | 108.1% → 109.7% | $243.8 → $309.7 (**+27%**) |
| Norwegian | 107.4% → 103.6% | $312.7 → $376.0 (+20%) |
| Carnival | 107.7% → 105.1% | $225.3 → $267.9 (+19%) |

Royal Caribbean has grown revenue per guest-day the most of the three, while keeping its ships at least as full as before. That is the work of pricing and revenue management.

---

## 7. How the real data is used

### a) Calibrating the synthetic bookings (`src/calibration.py`)
The synthetic generator was tuned until its quarterly **load factor** matched the real filings. Load factor here means guest-nights ÷ (2 × cabins × nights).

| Quarter | Synthetic | Royal Caribbean | Norwegian | Carnival |
|---|---:|---:|---:|---:|
| Q1 | 108.9% | 107.0% | 104.4% | 102.2% |
| Q2 | 109.7% | 108.5% | 106.1% | 103.6% |
| Q3 | 111.8% | 111.2% | 108.8% | 111.6% |
| Q4 | 106.4% | 106.9% | 103.2% | 102.0% |
| **Year** | **109.2%** | **108.4%** | 105.6% | 104.8% |

### b) Real-data forecast (`src/real_forecast.py`)
This forecasts **next quarter's revenue per passenger cruise day** for each company.

**Inputs:**
- same quarter last year
- last quarter's year-over-year growth
- seasonality and company
- the economic indicators: consumer sentiment, airfare inflation and unemployment, each averaged per quarter and **lagged one quarter**, so only information available before the quarter is used

**Model:** a damped growth trend plus a ridge-regression adjustment, pooled across the three companies.

**Validation:** walk-forward from Q2 2024 to Q3 2026. Each quarter is predicted using only earlier quarters. The model's settings are chosen by a **nested** walk-forward inside the training data, so the test quarters never influence them.

| Error (MAPE) | Same quarter last year | Last year × recent growth | **Model** |
|---|---:|---:|---:|
| Royal Caribbean (10 quarters) | 2.9% | 1.6% | **1.2%** |
| All three companies (28 quarters) | 3.6% | 1.6% | **1.5%** |

**Q4 2026 forecast for Royal Caribbean:** **$283 per passenger cruise day** (80% range $278–$287), vs. $282 in Q4 2025. You can check it against Royal Caribbean's next earnings release.

### c) Power BI
- The **Real Cruise Lines (SEC)** page shows quarterly occupancy and revenue per passenger day for all three companies, and the calibration check.
- The **Royal Caribbean Real Forecast** page shows the forecast against both baselines.

---

## 8. Reproduce it

```powershell
.\.venv\Scripts\Activate.ps1
$env:SEC_USER_AGENT = "Your Name your-email@example.com"   # the SEC asks automated clients to identify themselves
python -m src.sec_cruise_data    # downloads and parses the filings (a few minutes the first time; cached after)
python -m src.real_forecast      # downloads BLS + Michigan data, runs the walk-forward test
python -m src.sec_citations      # rebuilds docs/SEC_FILINGS.md and outputs/sec_filings_used.csv from the cache
python -m src.pipeline           # everything else, including calibration, charts and Power BI tables
```

---

## 9. Limitations

**The real data is quarterly and company-wide.** It doesn't show individual sailings, ships, cabin prices or bookings. That's why the booking-level analysis uses calibrated synthetic data.

**Revenue per PCD is total revenue ÷ passenger days.** It's a close stand-in for the companies' own "Net Yield", but not identical: Net Yield subtracts commissions and some onboard costs, and uses capacity instead of passenger days.

**Fiscal calendars differ.** Carnival's quarters end in Feb, May, Aug and Nov, and are matched to the nearest calendar quarter.

**There isn't much data:** about 60 usable company-quarters for the forecast, after removing COVID-19 quarters and the quarters with no same-quarter-last-year value. Every result is checked against simple baselines on quarters the model never saw.

---

## 10. References

All sources were retrieved in November 2026.

**Company filings: U.S. Securities and Exchange Commission, EDGAR**

1. Royal Caribbean Cruises Ltd. (2017–2026). *Forms 10-Q and 10-K, fiscal years 2017–2026* (CIK 0000884887). U.S. Securities and Exchange Commission. https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000884887&type=10-&dateb=&owner=include&count=40
2. Norwegian Cruise Line Holdings Ltd. (2016–2026). *Forms 10-Q and 10-K, fiscal years 2016–2026* (CIK 0001513761). U.S. Securities and Exchange Commission. https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001513761&type=10-&dateb=&owner=include&count=40
3. Carnival Corporation & plc (2016–2026). *Forms 10-Q and 10-K, fiscal years 2016–2026* (CIK 0000815097). U.S. Securities and Exchange Commission. https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000815097&type=10-&dateb=&owner=include&count=40
4. Royal Caribbean Cruises Ltd. (2026). *Form 10-Q for the quarterly period ended September 30, 2026*. U.S. Securities and Exchange Commission. https://www.sec.gov/Archives/edgar/data/884887/000088488726000044/rcl-20260930.htm
5. Norwegian Cruise Line Holdings Ltd. (2026). *Form 10-Q for the quarterly period ended September 30, 2026*. U.S. Securities and Exchange Commission. https://www.sec.gov/Archives/edgar/data/1513761/000110465926120217/nclh-20260930x10q.htm
6. Carnival Corporation & plc (2026). *Form 10-Q for the quarterly period ended August 31, 2026*. U.S. Securities and Exchange Commission. https://www.sec.gov/Archives/edgar/data/815097/000081509726000107/ccl-20260831.htm
7. Royal Caribbean Cruises Ltd. (2020). *Form 10-K for the fiscal year ended December 31, 2019*. U.S. Securities and Exchange Commission. https://www.sec.gov/Archives/edgar/data/884887/000088488720000009/rcl-20191231.htm

A citation for each of the 102 filings is in [SEC_FILINGS.md](SEC_FILINGS.md#citations).

**SEC data services**

8. U.S. Securities and Exchange Commission. *EDGAR Application Programming Interfaces (submissions and XBRL company facts)*. https://www.sec.gov/search-filings/edgar-application-programming-interfaces
9. U.S. Securities and Exchange Commission. *XBRL company facts*: [Royal Caribbean](https://data.sec.gov/api/xbrl/companyfacts/CIK0000884887.json), [Norwegian](https://data.sec.gov/api/xbrl/companyfacts/CIK0001513761.json), [Carnival](https://data.sec.gov/api/xbrl/companyfacts/CIK0000815097.json).

**Economic data**

10. U.S. Bureau of Labor Statistics. *Consumer Price Index for All Urban Consumers: Airline Fares in U.S. City Average, Seasonally Adjusted* (Series CUSR0000SETG01). https://data.bls.gov/timeseries/CUSR0000SETG01
11. U.S. Bureau of Labor Statistics. *Labor Force Statistics from the Current Population Survey: Unemployment Rate, Seasonally Adjusted* (Series LNS14000000). https://data.bls.gov/timeseries/LNS14000000
12. U.S. Bureau of Labor Statistics. *Public Data API*. https://www.bls.gov/developers/
13. University of Michigan, Surveys of Consumers. *Index of Consumer Sentiment* (monthly). https://www.sca.isr.umich.edu/ (data file: https://www.sca.isr.umich.edu/files/tbmics.csv)
