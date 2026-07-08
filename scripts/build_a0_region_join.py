#!/usr/bin/env python3
"""
A0 — Integrar clasificación de región natural al summary y al universo Movistar.

Outputs:
  outputs/observable/data/observable_4g_upgrade_summary_with_ubigeo.csv  (actualizado)
  outputs/tables/movistar_universe_with_region.csv
"""
from pathlib import Path
import unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

RC_PATH   = ROOT / "data/inei_cpv2017/region_classification_by_ubigeo.csv"
SUM_PATH  = ROOT / "outputs/observable/data/observable_4g_upgrade_summary_with_ubigeo.csv"
RAW_DIR   = ROOT / "data/raw"
OUT_UNI   = ROOT / "outputs/tables/movistar_universe_with_region.csv"

REGION_COLS = ["region3", "altitud_m", "poblacion_distrito"]


def norm(s):
    if not isinstance(s, str):
        s = str(s)
    s = s.strip().upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace(".", "").replace(",", "").replace("-", " ")
    return " ".join(s.split())


def load_rc():
    rc = pd.read_csv(RC_PATH, dtype=str)
    rc["ubigeo"] = rc["ubigeo"].str.zfill(6)
    rc["_key"] = rc["departamento"].map(norm) + "|" + rc["provincia"].map(norm) + "|" + rc["distrito"].map(norm)
    rc["altitud_m"] = pd.to_numeric(rc["altitud_m"], errors="coerce")
    rc["poblacion_distrito"] = pd.to_numeric(rc["poblacion_distrito"], errors="coerce")
    return rc


# ── 1. Summary de los 86 tratados ────────────────────────────────────────────
rc = load_rc()
rc_by_ubigeo = rc.set_index("ubigeo")[REGION_COLS]
rc_by_key    = rc.set_index("_key")[REGION_COLS]

summary = pd.read_csv(SUM_PATH)
summary["ubigeo"] = summary["ubigeo"].astype(str).str.zfill(6)
summary["_key"]   = summary["department"].map(norm) + "|" + summary["province"].map(norm) + "|" + summary["district"].map(norm)

# join primario por UBIGEO
for col in REGION_COLS:
    summary[col] = summary["ubigeo"].map(rc_by_ubigeo[col])

# fallback por nombre para los que no matchearon por UBIGEO
mask_missing = summary["region3"].isna()
if mask_missing.any():
    for col in REGION_COLS:
        summary.loc[mask_missing, col] = summary.loc[mask_missing, "_key"].map(rc_by_key[col])

summary = summary.drop(columns=["_key"])
summary.to_csv(SUM_PATH, index=False, encoding="utf-8")

# ── Log QA ───────────────────────────────────────────────────────────────────
print(f"Summary tratados: {len(summary)} filas")
print(f"  region3 NaN   : {summary['region3'].isna().sum()}")
print(f"  region3 valores: {sorted(summary['region3'].dropna().unique())}")
print()
print("QA manual:")
checks = {
    "Puno":   ("Sierra", "department"),
    "Callao": ("Costa",  "department"),
    "Cusco":  ("Sierra", "department"),
    "Lima":   ("Costa",  "department"),
}
for name, (expected, col) in checks.items():
    rows = summary[summary[col].str.upper() == name.upper()]
    vals = rows["region3"].unique().tolist()
    ok = all(v == expected for v in vals if pd.notna(v))
    print(f"  {name}: region3={vals} {'OK' if ok else 'FALLO'}")
print()
print("Muestra de clasificaciones:")
print(summary[["department","province","district","ubigeo","region3","altitud_m","poblacion_distrito"]].head(10).to_string(index=False))

# ── 2. Universo completo Movistar ─────────────────────────────────────────────
print("\nCargando universo Movistar...")
dfs = []
for f in sorted(RAW_DIR.glob("dataset_*.csv")):
    df = pd.read_csv(f, sep=";", dtype=str)
    df["SOURCE_FILE"] = f.name
    dfs.append(df)
raw = pd.concat(dfs, ignore_index=True)
raw = raw[raw["NETWORK_CARRIER"].str.upper().str.strip() == "MOVISTAR"]

universe = (
    raw[["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME"]]
    .drop_duplicates()
    .rename(columns={"ADM_LEVEL_1_NAME": "department",
                     "ADM_LEVEL_2_NAME": "province",
                     "ADM_LEVEL_3_NAME": "district"})
    .copy()
)
universe["_key"] = universe["department"].map(norm) + "|" + universe["province"].map(norm) + "|" + universe["district"].map(norm)

for col in REGION_COLS:
    universe[col] = universe["_key"].map(rc_by_key[col])

universe = universe.drop(columns=["_key"])
universe.to_csv(OUT_UNI, index=False, encoding="utf-8")

n_matched   = universe["region3"].notna().sum()
n_unmatched = universe["region3"].isna().sum()
print(f"Universo Movistar: {len(universe)} distritos únicos")
print(f"  Con region3    : {n_matched} ({100*n_matched/len(universe):.1f}%)")
print(f"  Sin region3    : {n_unmatched} ({100*n_unmatched/len(universe):.1f}%)")
if n_unmatched:
    print("  Unmatched (primeros 10):")
    for _, r in universe[universe["region3"].isna()].head(10).iterrows():
        print(f"    {r['department']} | {r['province']} | {r['district']}")

# ── Asserts ───────────────────────────────────────────────────────────────────
assert summary["region3"].isna().sum() == 0, "ASSERT FAIL: hay NaN en region3 para los 86 tratados"
assert set(summary["region3"].unique()) <= {"Costa", "Sierra", "Selva"}, "ASSERT FAIL: valor inesperado en region3"
print("\nTodos los asserts OK.")
