#!/usr/bin/env python3
"""
A3 — Tests de significancia: Wilcoxon, Bootstrap IC 95%, Spearman, Robustez.

Inputs:
  outputs/observable/data/observable_4g_upgrade_summary_with_ubigeo.csv
  outputs/tables/did_summary.csv

Output:
  outputs/tables/observable_stats.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as spstats

ROOT    = Path(__file__).resolve().parents[1]
SUM_PATH = ROOT / "outputs" / "observable" / "data" / "observable_4g_upgrade_summary_with_ubigeo.csv"
DID_PATH = ROOT / "outputs" / "tables" / "did_summary.csv"
OUT_JSON = ROOT / "outputs" / "tables" / "observable_stats.json"

MIN_VALID   = 3    # meses post minimos para analisis
BOOT_SEED   = 42
BOOT_N      = 10_000
EXCL_MEAS   = 1_000  # mediciones/mes minimo para variante robustez


def bootstrap_median_ci(data: np.ndarray, n_boot: int = BOOT_N, ci: float = 0.95, rng=None):
    if rng is None:
        rng = np.random.default_rng(BOOT_SEED)
    medians = np.array([
        np.median(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_boot)
    ])
    alpha = (1 - ci) / 2
    return float(np.median(data)), float(np.percentile(medians, 100 * alpha)), float(np.percentile(medians, 100 * (1 - alpha)))


def wilcoxon_greater(data: np.ndarray) -> tuple[float, float]:
    res = spstats.wilcoxon(data, alternative="greater")
    return float(res.statistic), float(res.pvalue)


def _round_p(p: float) -> float:
    """Guarda suficiente precision para p-values muy pequenos (no redondear a 0)."""
    return float(f"{p:.2e}") if p < 1e-4 else round(p, 6)


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    mask = x.notna() & y.notna()
    if mask.sum() < 5:
        return float("nan"), float("nan")
    r, p = spstats.spearmanr(x[mask], y[mask])
    return float(r), float(p)


def main() -> None:
    rng = np.random.default_rng(BOOT_SEED)

    # ── Cargar datos ─────────────────────────────────────────────────────────────
    full = pd.read_csv(SUM_PATH)
    full["log10_pop"] = np.log10(pd.to_numeric(full["poblacion_distrito"], errors="coerce").clip(lower=1))

    n_confirmed = len(full)

    # Subconjunto de analisis: >= MIN_VALID meses post
    df = full[full["months_post"] >= MIN_VALID].copy()
    n_analysis = len(df)

    n_departments = df["department"].nunique()

    bp_min = int(df["breakpoint_yearmonth"].min())
    bp_max = int(df["breakpoint_yearmonth"].max())

    print(f"n_confirmed = {n_confirmed}")
    print(f"n_analysis  = {n_analysis}  (months_post >= {MIN_VALID})")
    print(f"n_departments = {n_departments}")
    print()

    # ── DiD ──────────────────────────────────────────────────────────────────────
    did_df   = pd.read_csv(DID_PATH)
    matched  = did_df[~did_df["unmatched"]].copy()
    did_vec  = matched["did"].dropna().values
    n_matched   = len(matched)
    n_unmatched = int(did_df["unmatched"].sum())

    # ── A3.1 Wilcoxon ────────────────────────────────────────────────────────────
    delta_crude = df["delta_4g_download_mbps"].dropna().values
    w_stat_crude, w_p_crude = wilcoxon_greater(delta_crude)
    print(f"Wilcoxon delta crudo : W={w_stat_crude:.1f}  p={w_p_crude:.4f}  (n={len(delta_crude)})")

    w_stat_did, w_p_did = wilcoxon_greater(did_vec)
    print(f"Wilcoxon DiD         : W={w_stat_did:.1f}  p={w_p_did:.4f}  (n={len(did_vec)})")

    # ── A3.2 Bootstrap IC 95% ────────────────────────────────────────────────────
    med_crude, ci_crude_lo, ci_crude_hi = bootstrap_median_ci(delta_crude, rng=rng)
    print(f"\nBootstrap delta crudo  : med={med_crude:.4f}  IC95=[{ci_crude_lo:.4f}, {ci_crude_hi:.4f}]")

    med_did, ci_did_lo, ci_did_hi = bootstrap_median_ci(did_vec, rng=rng)
    print(f"Bootstrap DiD          : med={med_did:.4f}  IC95=[{ci_did_lo:.4f}, {ci_did_hi:.4f}]")

    delta_lat = df["delta_4g_latency_ms"].dropna().values
    med_lat, ci_lat_lo, ci_lat_hi = bootstrap_median_ci(delta_lat, rng=rng)
    print(f"Bootstrap delta latency: med={med_lat:.4f}  IC95=[{ci_lat_lo:.4f}, {ci_lat_hi:.4f}]")

    # ── A3.3 Spearman ────────────────────────────────────────────────────────────
    rho_lat,  p_lat  = spearman(df["delta_4g_download_mbps"], df["delta_4g_latency_ms"])
    rho_base, p_base = spearman(df["delta_4g_download_mbps"], df["pre6_4g_download_mbps"])
    rho_pop,  p_pop  = spearman(df["delta_4g_download_mbps"], df["log10_pop"])
    rho_alt,  p_alt  = spearman(df["delta_4g_download_mbps"], df["altitud_m"])

    print(f"\nSpearman delta_dl vs latency  : rho={rho_lat:.3f}  p={p_lat:.4f}")
    print(f"Spearman delta_dl vs baseline : rho={rho_base:.3f}  p={p_base:.4f}")
    print(f"Spearman delta_dl vs log_pop  : rho={rho_pop:.3f}  p={p_pop:.4f}")
    print(f"Spearman delta_dl vs altitud  : rho={rho_alt:.3f}  p={p_alt:.4f}")

    # ── A3.4 Robustez ────────────────────────────────────────────────────────────
    def r4(x): return round(float(x), 4)

    # Principal: mediana no ponderada, >=MIN_VALID post
    rob_principal = {"median": r4(np.median(delta_crude)), "n": int(len(delta_crude))}

    # Ponderada: media ponderada (weighted)
    delta_w = df["delta_4g_download_mbps_weighted"].dropna()
    rob_weighted = {"median": r4(delta_w.median()), "mean": r4(delta_w.mean()), "n": int(len(delta_w))}

    # Strict post: >=6 meses post
    df_strict = df[df["months_post"] >= 6].copy()
    rob_strict = {"median": r4(df_strict["delta_4g_download_mbps"].median()), "n": int(len(df_strict))}

    # DiD
    rob_did = {"median": r4(np.median(did_vec)), "mean": r4(did_vec.mean()), "n": int(len(did_vec))}

    # Excl. outliers (<1000 meas/mes promedio)
    df["avg_meas_per_month"] = (
        (df["pre6_4g_download_measurements"].fillna(0) + df["post6_4g_download_measurements"].fillna(0))
        / (df["months_pre"] + df["months_post"])
    )
    df_hi_meas = df[df["avg_meas_per_month"] >= EXCL_MEAS].copy()
    rob_excl = {"median": r4(df_hi_meas["delta_4g_download_mbps"].median()), "n": int(len(df_hi_meas))}

    print(f"\nRobustez:")
    print(f"  Principal       : med={rob_principal['median']:.4f}  n={rob_principal['n']}")
    print(f"  Ponderada (wtd) : med={rob_weighted['median']:.4f}  n={rob_weighted['n']}")
    print(f"  Strict post>=6  : med={rob_strict['median']:.4f}  n={rob_strict['n']}")
    print(f"  DiD             : med={rob_did['median']:.4f}  n={rob_did['n']}")
    print(f"  Excl. <{EXCL_MEAS}med/m : med={rob_excl['median']:.4f}  n={rob_excl['n']}")

    # ── By region ────────────────────────────────────────────────────────────────
    by_region = {}
    for region, grp in df.groupby("region3"):
        key = str(region).lower()
        d = grp["delta_4g_download_mbps"].dropna()
        by_region[key] = {
            "n": int(len(grp)),
            "median": round(float(d.median()), 4),
            "mean":   round(float(d.mean()),   4),
        }
    print(f"\nPor region: {by_region}")

    # ── Asserts ──────────────────────────────────────────────────────────────────
    print()
    assert w_p_did < 0.05, f"ASSERT FAIL: Wilcoxon DiD p={w_p_did:.4f} >= 0.05 — revisar narrativa"
    print(f"Assert Wilcoxon DiD p<0.05: OK (p={w_p_did:.4f})")

    assert ci_did_lo > 0, f"ASSERT FAIL: IC95 DiD cruza cero [{ci_did_lo:.4f}, {ci_did_hi:.4f}]"
    print(f"Assert IC95 DiD no cruza 0: OK [{ci_did_lo:.4f}, {ci_did_hi:.4f}]")

    variants_medians = [
        rob_principal["median"], rob_weighted["median"],
        rob_strict["median"],    rob_did["median"], rob_excl["median"],
    ]
    assert all(v > 0 for v in variants_medians), f"ASSERT FAIL: variante con mediana <= 0: {variants_medians}"
    print(f"Assert todas variantes > 0: OK {[round(v,3) for v in variants_medians]}")

    # ── Construir JSON ────────────────────────────────────────────────────────────
    stats = {
        "dataset": {
            "n_confirmed":    n_confirmed,
            "n_analysis":     n_analysis,
            "n_departments":  n_departments,
            "bp_range":       f"{bp_min}-{bp_max}",
        },
        "delta_crude": {
            "median":          round(med_crude, 4),
            "mean":            round(float(delta_crude.mean()), 4),
            "std":             round(float(delta_crude.std()),  4),
            "ci95_lo":         round(ci_crude_lo, 4),
            "ci95_hi":         round(ci_crude_hi, 4),
            "wilcoxon_stat":   round(w_stat_crude, 1),
            "wilcoxon_p":      _round_p(w_p_crude),
            "n_positive":      int((delta_crude > 0).sum()),
            "n_negative":      int((delta_crude < 0).sum()),
            "n":               int(len(delta_crude)),
        },
        "delta_weighted": {
            "median": round(rob_weighted["median"], 4),
            "mean":   round(rob_weighted["mean"],   4),
            "n":      rob_weighted["n"],
        },
        "delta_latency": {
            "median":  round(med_lat, 4),
            "ci95_lo": round(ci_lat_lo, 4),
            "ci95_hi": round(ci_lat_hi, 4),
            "n":       int(len(delta_lat)),
        },
        "did": {
            "median":        round(med_did, 4),
            "mean":          round(float(did_vec.mean()), 4),
            "std":           round(float(did_vec.std()),  4),
            "ci95_lo":       round(ci_did_lo, 4),
            "ci95_hi":       round(ci_did_hi, 4),
            "wilcoxon_stat": round(w_stat_did, 1),
            "wilcoxon_p":    _round_p(w_p_did),
            "n_positive":    int((did_vec > 0).sum()),
            "n_negative":    int((did_vec < 0).sum()),
            "n_matched":     n_matched,
            "n_unmatched":   n_unmatched,
        },
        "by_region": by_region,
        "correlations": {
            "delta_dl_vs_latency":        {"rho": round(rho_lat,  4), "p": _round_p(p_lat)},
            "delta_dl_vs_baseline":       {"rho": round(rho_base, 4), "p": _round_p(p_base)},
            "delta_dl_vs_log_poblacion":  {"rho": round(rho_pop,  4), "p": _round_p(p_pop)},
            "delta_dl_vs_altitud":        {"rho": round(rho_alt,  4), "p": _round_p(p_alt)},
        },
        "robustness": {
            "principal":      rob_principal,
            "weighted":       rob_weighted,
            "strict_post6":   rob_strict,
            "did":            rob_did,
            "excl_low_meas":  rob_excl,
        },
        "bootstrap": {
            "seed":         BOOT_SEED,
            "n_iterations": BOOT_N,
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEscrito: {OUT_JSON}")


if __name__ == "__main__":
    main()
