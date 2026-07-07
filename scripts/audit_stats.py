#!/usr/bin/env python3
"""
Audit statistics for the OSIPTEL 3G shutdown pipeline.
Generates numbers used in AUDIT.md. Does not modify any pipeline logic.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portalosiptel3g.cleaning import clean_minimal
from portalosiptel3g.features import add_yearmonth, add_3g_flags
from portalosiptel3g.io import read_and_concat

SEP = "-" * 60

# ── Load raw data ──────────────────────────────────────────────
print(SEP)
print("LOADING RAW DATA")
raw = read_and_concat(ROOT / "data" / "raw", pattern="dataset_*.csv")
raw = clean_minimal(raw)
raw = add_yearmonth(raw)
raw = add_3g_flags(raw)
raw_mv = raw[raw["NETWORK_CARRIER"] == "MOVISTAR"].copy()

KEYS = ["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME"]

# ── 1. Temporal coverage ───────────────────────────────────────
print(SEP)
print("TEMPORAL COVERAGE")
ym_min = int(raw_mv["YEARMONTH"].min())
ym_max = int(raw_mv["YEARMONTH"].max())
print(f"  First YEARMONTH : {ym_min}")
print(f"  Last  YEARMONTH : {ym_max}")
n_months_global = raw_mv["YEARMONTH"].nunique()
print(f"  Distinct months in dataset: {n_months_global}")

# ── 2. District counts ─────────────────────────────────────────
print(SEP)
print("DISTRICT COUNTS (MOVISTAR)")
raw_districts = raw_mv.groupby(KEYS).ngroups
print(f"  Unique Movistar districts in raw CSVs : {raw_districts}")

shutdown = pd.read_csv(ROOT / "outputs" / "tables" / "shutdown_confirmed.csv")
print(f"  Confirmed shutdown districts (all)    : {len(shutdown)}")

series = pd.read_csv(ROOT / "outputs" / "tables" / "dataset_2023_2025_shutdown_districts.csv")
summary = pd.read_csv(ROOT / "outputs" / "observable" / "data" / "observable_4g_upgrade_summary.csv")
filtered = summary[summary["months_post"] >= 3]
print(f"  Confirmed with >= 3 months post       : {len(filtered)}")

# ── 3. Districts per source year ───────────────────────────────
print(SEP)
print("DISTRICTS PER SOURCE FILE")
for src, g in raw_mv.groupby("SOURCE_FILE"):
    n = g.groupby(KEYS).ngroups
    yms = sorted(g["YEARMONTH"].unique())
    print(f"  {src}: {n} districts, months {yms[0]}-{yms[-1]}")

# ── 4. Districts appearing/disappearing between years ──────────
print(SEP)
print("DISTRICT STABILITY ACROSS YEARS")
by_year = {}
for src, g in raw_mv.groupby("SOURCE_FILE"):
    by_year[src] = set(g.groupby(KEYS).groups.keys())

files = sorted(by_year.keys())
for i in range(len(files) - 1):
    a, b = files[i], files[i + 1]
    only_a = by_year[a] - by_year[b]
    only_b = by_year[b] - by_year[a]
    print(f"  {a} -> {b}: disappeared={len(only_a)}, appeared={len(only_b)}")
    for d in sorted(only_a)[:5]:
        print(f"    DISAPPEARED: {d}")
    for d in sorted(only_b)[:5]:
        print(f"    APPEARED:    {d}")

# ── 5. Missing months vs zero values ──────────────────────────
print(SEP)
print("MISSING MONTHS vs ZERO VALUES (shutdown districts)")
data_merged = series.copy()
data_merged["YEARMONTH"] = pd.to_numeric(data_merged["YEARMONTH"], errors="coerce").astype(int)
data_merged = data_merged.merge(shutdown, on=KEYS + ["NETWORK_CARRIER"], how="inner")

months_global = sorted(raw_mv["YEARMONTH"].unique())

gap_count = 0
zero_rows = 0
total_district_months = 0
for key, g in data_merged.groupby(KEYS + ["NETWORK_CARRIER"], dropna=False):
    present = set(g["YEARMONTH"].tolist())
    bp = int(g["BREAKPOINT_YEARMONTH"].iloc[0])
    last_ym = int(g["YEARMONTH"].max())
    expected = [m for m in months_global if m <= last_ym]
    missing = [m for m in expected if m not in present]
    if missing:
        gap_count += 1
    zero_rows += int((g["IS_3G_ZERO_MONTH"]).sum())
    total_district_months += len(g)

print(f"  Districts with at least one missing month (gap) in full span: {gap_count}")
print(f"  Total IS_3G_ZERO_MONTH rows in shutdown districts: {zero_rows}")
print(f"  Total district-month rows: {total_district_months}")
print("  NOTE: clean_minimal fills empty string -> 0 for KPI cols.")
print("  A missing row (no CSV entry) is indistinguishable from a zero row after concat.")

# ── 6. Measurements distribution ──────────────────────────────
print(SEP)
print("MEASUREMENTS DISTRIBUTION (THROUGHPUT_DOWNLOAD_4G, pre+post 6-month window)")
data_merged2 = series.merge(shutdown, on=KEYS + ["NETWORK_CARRIER"], how="inner")
data_merged2["YEARMONTH"] = pd.to_numeric(data_merged2["YEARMONTH"], errors="coerce").astype(int)
data_merged2["BREAKPOINT_YEARMONTH"] = pd.to_numeric(data_merged2["BREAKPOINT_YEARMONTH"], errors="coerce").astype(int)
data_merged2["THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"] = pd.to_numeric(
    data_merged2["THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"], errors="coerce"
)

window_rows = []
for key, g in data_merged2.groupby(KEYS + ["NETWORK_CARRIER"], dropna=False):
    g = g.sort_values("YEARMONTH")
    bp = int(g["BREAKPOINT_YEARMONTH"].iloc[0])
    pre6 = g[g["YEARMONTH"] < bp].tail(6)
    post6 = g[g["YEARMONTH"] >= bp].head(6)
    for _, r in pd.concat([pre6, post6]).iterrows():
        window_rows.append(r["THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"])

meas = pd.Series(window_rows).dropna()
print(f"  n district-month rows in pre/post 6m windows: {len(meas)}")
print(f"  min={meas.min():.0f}  p25={meas.quantile(0.25):.0f}  "
      f"median={meas.median():.0f}  p75={meas.quantile(0.75):.0f}  max={meas.max():.0f}")
zero_meas = (meas == 0).sum()
print(f"  Rows with 0 measurements (no 4G data): {zero_meas} ({100*zero_meas/len(meas):.1f}%)")

# ── 7. Section 5: Descriptive stats for the paper ─────────────
print(SEP)
print("DESCRIPTIVE STATS — 86 confirmed")

print("\n  Breakdown by department:")
dept_counts = shutdown["ADM_LEVEL_1_NAME"].value_counts()
for dept, cnt in dept_counts.items():
    print(f"    {dept}: {cnt}")

print("\n  Breakpoint distribution:")
bp_dist = shutdown["BREAKPOINT_YEARMONTH"].value_counts().sort_index()
for ym, cnt in bp_dist.items():
    print(f"    {ym}: {cnt} districts")

print(SEP)
print("DESCRIPTIVE STATS — 68 filtered (months_post >= 3)")
delta = filtered["delta_4g_download_mbps"]
print(f"  n           = {len(filtered)}")
print(f"  mean        = {delta.mean():.4f} Mbps")
print(f"  median      = {delta.median():.4f} Mbps")
print(f"  std         = {delta.std():.4f} Mbps")
print(f"  min         = {delta.min():.4f} Mbps")
print(f"  max         = {delta.max():.4f} Mbps")
n_pos = (delta > 0).sum()
print(f"  delta > 0   = {n_pos} ({100*n_pos/len(filtered):.1f}%)")

print("\n  Months-post distribution:")
for n_mo, label in [(3, "3"), (6, "6"), (12, "12+")]:
    if label == "12+":
        cnt = (summary["months_post"] >= 12).sum()
    else:
        cnt = (summary["months_post"] == n_mo).sum()
    print(f"    months_post == {label}: {cnt}")
print(f"  Full distribution:")
print(summary["months_post"].value_counts().sort_index().to_string())

# ── 8. Control group candidates ───────────────────────────────
print(SEP)
print("CONTROL GROUP CANDIDATES")
shutdown_keys = set(
    zip(shutdown["ADM_LEVEL_1_NAME"], shutdown["ADM_LEVEL_2_NAME"],
        shutdown["ADM_LEVEL_3_NAME"], shutdown["NETWORK_CARRIER"])
)

months_all = sorted(raw_mv["YEARMONTH"].unique())
n_months_all = len(months_all)
ym_first = months_all[0]
ym_last = months_all[-1]

pure_control = 0
partial_control = 0
for key, g in raw_mv.groupby(KEYS + ["NETWORK_CARRIER"], dropna=False):
    if key in shutdown_keys:
        continue
    g = g.sort_values("YEARMONTH")
    active_months = set(g[g["IS_3G_ACTIVE_MONTH"] == True]["YEARMONTH"].tolist())
    n_active = len(active_months)
    if n_active == n_months_all:
        pure_control += 1
    elif n_active >= 10:
        partial_control += 1

print(f"  Non-shutdown Movistar districts with 3G active in ALL {n_months_all} months: {pure_control}")
print(f"  Non-shutdown Movistar districts with >= 10 active months (partial): {partial_control}")
print(f"  Total non-shutdown Movistar districts: {raw_districts - len(shutdown)}")

print(SEP)
print("DONE")
