"""Project-wide settings and paths."""
from pathlib import Path
import os

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_CLEAN = ROOT / "data" / "clean"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
POWERBI = OUTPUTS / "powerbi"
LOGS = ROOT / "logs"

# "Today" for the snapshot: bookings after this date don't exist yet.
# Override with the AS_OF environment variable or the pipeline's --as-of flag.
AS_OF = pd.Timestamp(os.environ.get("AS_OF", "2026-11-20"))

SEED = 42

# Sailings depart from FIRST_SAIL to LAST_SAIL. Sailings after AS_OF are still open.
FIRST_SAIL = pd.Timestamp("2024-01-01")
LAST_SAIL = pd.Timestamp("2027-06-30")

CATEGORIES = ["inside", "oceanview", "balcony", "suite"]

# Snapshot horizons (days before sailing) the forecast model learns from.
HORIZONS = [7, 14, 30, 60, 90, 120, 180]

# Backtest: the most recent departed sailings are held out for testing.
TEST_MONTHS = 6

for p in (DATA_RAW, DATA_CLEAN, OUTPUTS, FIGURES, POWERBI, LOGS):
    p.mkdir(parents=True, exist_ok=True)
