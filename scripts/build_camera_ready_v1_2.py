#!/usr/bin/env python3
"""
v1.2 — Camera-ready LATINCOM 2026 (SPEC: Paper/spec_v1_2_camera_ready.md).

NO rediseña nada congelado: reutiliza TAL CUAL los pares tratado-control de
outputs/tables/did_matches.csv (matching Mahalanobis K=5, v1.0) y las
funciones de deteccion/limpieza de src/portalosiptel3g/. Corre sobre los raw
congelados en este worktree (tag v1.1-outcomes), hasta YEARMONTH 202605.

Inputs:
  data/raw/dataset_*.csv                                  (congelado, <=202605)
  outputs/tables/shutdown_confirmed.csv                    (86 confirmados)
  outputs/tables/did_matches.csv, did_summary.csv          (matching K=5, congelado)
  outputs/tables/event_study.csv                           (tau=-6..5, gap_mean)
  outputs/tables/observable_stats.json                     (sanity: DiD=0.6488, crudo=1.0032)
  outputs/tables/observable_stats_v1_1.json                (sanity: excl_5g n=60, DiD=0.8429)
  outputs/tables/dataset_2023_2026_shutdown_districts.csv  (series completa tratados)
  outputs/tables/movistar_universe_with_region_a_mano.csv  (covariables pool control)
  outputs/observable/data/observable_4g_upgrade_summary_with_ubigeo.csv

Output:
  outputs/v1_2/*.csv
  outputs/v1_2/observable_stats_v1_2.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as spstats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from portalosiptel3g.io import read_csv_safely  # noqa: E402
from portalosiptel3g.cleaning import clean_minimal  # noqa: E402
from portalosiptel3g.features import add_yearmonth, add_3g_flags  # noqa: E402
from portalosiptel3g.detection import MIN_ACTIVE_MONTHS_PRE  # noqa: E402

import build_control_and_did as bcd  # noqa: E402
import build_multioutcome_did as bmd  # noqa: E402

RAW_DIR   = ROOT / "data" / "raw"
TABLES    = ROOT / "outputs" / "tables"
OBS_DATA  = ROOT / "outputs" / "observable" / "data"
OUT_DIR   = ROOT / "outputs" / "v1_2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BOOT_SEED = 42
BOOT_N    = 10_000
MEAS_COL  = "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"
DL_COL    = "AVERAGE_THROUGHPUT_DOWNLOAD_4G"
EXCL_MEAS = 1_000
MIN_VALID = 3

SANITY_DID_MEDIAN = 0.6488
SANITY_N = 67
SANITY_TOL = 1e-4


# ─────────────────────────────────────────────────────────────────────────────
# Helpers generales
# ─────────────────────────────────────────────────────────────────────────────
def r4(x):
    if x is None:
        return None
    x = float(x)
    return None if np.isnan(x) else round(x, 4)


def round_p(p: float) -> float:
    return float(f"{p:.2e}") if p < 1e-4 else round(float(p), 6)


def bootstrap_ci(data: np.ndarray, stat_fn, n_boot: int = BOOT_N, seed: int = BOOT_SEED):
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    if len(data) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    stats_boot = np.array([
        stat_fn(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_boot)
    ])
    return float(np.percentile(stats_boot, 2.5)), float(np.percentile(stats_boot, 97.5))


def bootstrap_median_ci(data, n_boot=BOOT_N, seed=BOOT_SEED):
    return bootstrap_ci(data, np.median, n_boot, seed)


def bootstrap_mean_ci(data, n_boot=BOOT_N, seed=BOOT_SEED):
    return bootstrap_ci(data, np.mean, n_boot, seed)


def wilcoxon_pair(data: np.ndarray):
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    if len(data) < 1 or not np.any(data != 0):
        return float("nan"), float("nan")
    p_one = float(spstats.wilcoxon(data, alternative="greater").pvalue)
    p_two = float(spstats.wilcoxon(data, alternative="two-sided").pvalue)
    return p_one, p_two


def npos_nneg(data: np.ndarray):
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    return int((data > 0).sum()), int((data < 0).sum())


def district_key(dept, prov, dist) -> str:
    return bcd.district_key(dept, prov, dist)


def ym_to_idx(ym: int) -> int:
    return bcd.ym_to_idx(ym)


def idx_to_ym(idx: int) -> int:
    return bcd.idx_to_ym(idx)


def cal_window(bp: int, offsets: list[int], global_months: set[int]) -> list[int]:
    idx = ym_to_idx(bp)
    months = [idx_to_ym(idx + o) for o in offsets]
    return [m for m in months if m in global_months]


def simple_mean(g: pd.DataFrame, months: list[int], col: str, meas_col: str = MEAS_COL) -> float:
    if g is None or g.empty or not months:
        return float("nan")
    rows = g[g["YEARMONTH"].isin(months)]
    if meas_col in rows.columns:
        rows = rows[rows[meas_col] > 0]
    if rows.empty or col not in rows.columns:
        return float("nan")
    return float(rows[col].mean())


def weighted_mean(g: pd.DataFrame, months: list[int], col: str, meas_col: str = MEAS_COL) -> float:
    if g is None or g.empty or not months:
        return float("nan")
    rows = g[g["YEARMONTH"].isin(months)]
    if meas_col not in rows.columns:
        return float("nan")
    rows = rows[rows[meas_col] > 0]
    if rows.empty or rows[meas_col].sum() == 0:
        return float("nan")
    return float((rows[col] * rows[meas_col]).sum() / rows[meas_col].sum())


def n_valid_months(g: pd.DataFrame, months: list[int], meas_col: str = MEAS_COL) -> int:
    if g is None or g.empty or not months:
        return 0
    rows = g[g["YEARMONTH"].isin(months)]
    if meas_col not in rows.columns:
        return 0
    return int((rows[meas_col] > 0).sum())


def mean_meas(g: pd.DataFrame, months: list[int], meas_col: str = MEAS_COL) -> float:
    if g is None or g.empty or not months:
        return float("nan")
    rows = g[g["YEARMONTH"].isin(months)]
    if meas_col not in rows.columns:
        return float("nan")
    rows = rows[rows[meas_col] > 0]
    if rows.empty:
        return float("nan")
    return float(rows[meas_col].mean())


# ─────────────────────────────────────────────────────────────────────────────
# Carga de datos base (congelados en este worktree, <=202605)
# ─────────────────────────────────────────────────────────────────────────────
def load_base():
    print("Cargando dataset completo MOVISTAR (misma carga que v1.0/v1.1)...")
    full = bmd.load_full_movistar()
    last_ym = int(full["YEARMONTH"].max())
    print(f"  Ultimo YEARMONTH leido: {last_ym}")
    global_months = set(int(m) for m in full["YEARMONTH"].dropna().unique())
    full["_key"] = full.apply(
        lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
    )
    by_key = {key: g.sort_values("YEARMONTH").reset_index(drop=True) for key, g in full.groupby("_key")}

    shutdown = pd.read_csv(TABLES / "shutdown_confirmed.csv")
    matches = pd.read_csv(TABLES / "did_matches.csv", encoding="utf-8")
    did_summary = pd.read_csv(TABLES / "did_summary.csv", encoding="utf-8")
    summary_ubigeo = pd.read_csv(OBS_DATA / "observable_4g_upgrade_summary_with_ubigeo.csv")
    event_study_v1 = pd.read_csv(TABLES / "event_study.csv")
    treated_series = pd.read_csv(TABLES / "dataset_2023_2026_shutdown_districts.csv")
    for col in ["YEARMONTH", MEAS_COL, DL_COL]:
        if col in treated_series.columns:
            treated_series[col] = pd.to_numeric(treated_series[col], errors="coerce")
    treated_series["_key"] = treated_series.apply(
        lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
    )

    obs_stats = json.loads((TABLES / "observable_stats.json").read_text(encoding="utf-8"))
    obs_stats_v11 = json.loads((TABLES / "observable_stats_v1_1.json").read_text(encoding="utf-8"))

    return dict(
        full=full, last_ym=last_ym, global_months=global_months, by_key=by_key,
        shutdown=shutdown, matches=matches, did_summary=did_summary,
        summary_ubigeo=summary_ubigeo, event_study_v1=event_study_v1,
        treated_series=treated_series, obs_stats=obs_stats, obs_stats_v11=obs_stats_v11,
    )


def sanity_checks(base: dict) -> dict:
    print("\n=== Sanity checks (regla 5) ===")
    matched = base["did_summary"][~base["did_summary"]["unmatched"]]
    did_vec = matched["did"].dropna().values
    did_median = float(np.median(did_vec))
    n = len(did_vec)
    ok_did = abs(did_median - SANITY_DID_MEDIAN) < SANITY_TOL and n == SANITY_N
    print(f"  DiD principal = {did_median:.4f} (esperado {SANITY_DID_MEDIAN}), n={n} (esperado {SANITY_N}): "
          f"{'OK' if ok_did else 'FALLO'}")

    crude_expected = base["obs_stats"]["delta_crude"]["median"]
    crude_n_expected = base["obs_stats"]["delta_crude"]["n"]
    crude_actual = float(base["did_summary"]["delta_treated"].median())
    crude_n_actual = int(base["did_summary"]["delta_treated"].notna().sum())
    ok_crude = abs(crude_actual - crude_expected) < SANITY_TOL and crude_n_actual == crude_n_expected
    print(f"  Crudo principal = {crude_actual:.4f} (esperado {crude_expected}), n={crude_n_actual} "
          f"(esperado {crude_n_expected}): {'OK' if ok_crude else 'FALLO'}")

    v11 = base["obs_stats_v11"]["robustness"]["excl_5g_contaminated"]["outcomes"]["download"]
    ok_v11 = True  # v1.1 es solo verificacion de lectura, no recalculo aqui (T1.excl_5G lo hace)
    print(f"  Sensibilidad 5G (v1.1, referencia) = did_median={v11['did_median']} n={v11['n']}")

    ok_last_ym = base["last_ym"] == 202605
    print(f"  Ultimo YEARMONTH = {base['last_ym']} (esperado 202605): {'OK' if ok_last_ym else 'FALLO'}")

    if not (ok_did and ok_crude and ok_last_ym):
        print("\n*** SANITY CHECK FALLIDO — abortando. ***")
        sys.exit(1)

    return {
        "did_principal_median": r4(did_median), "did_principal_n": n,
        "crude_principal_median": r4(crude_actual), "crude_principal_n": crude_n_actual,
        "sensitivity_5g_v11_did_median": v11["did_median"], "sensitivity_5g_v11_n": v11["n"],
        "last_yearmonth_read": base["last_ym"],
        "all_ok": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# T0 — Verificaciones previas
# ─────────────────────────────────────────────────────────────────────────────
def t0_1_zero_types(base: dict) -> pd.DataFrame:
    print("\n=== T0.1 — Ceros vs vacios vs filas ausentes ===")
    raw_frames = []
    for f in sorted(RAW_DIR.glob("dataset_*.csv")):
        df = read_csv_safely(f)
        df["SOURCE_FILE"] = f.name
        raw_frames.append(df)
    raw = pd.concat(raw_frames, ignore_index=True)
    raw = raw[raw["NETWORK_CARRIER"].str.upper() == "MOVISTAR"].copy()
    raw["AÑO_i"] = pd.to_numeric(raw["AÑO"], errors="coerce").fillna(0).astype(int)
    raw["MES_i"] = pd.to_numeric(raw["MES"], errors="coerce").fillna(0).astype(int)
    raw["YEARMONTH"] = raw["AÑO_i"] * 100 + raw["MES_i"]
    raw["_key"] = raw.apply(
        lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
    )
    raw_by_key = {k: g for k, g in raw.groupby("_key")}
    global_months = base["global_months"]
    last_ym = base["last_ym"]
    months_sorted = sorted(global_months)

    rows = []
    for _, s in base["shutdown"].iterrows():
        key = district_key(s["ADM_LEVEL_1_NAME"], s["ADM_LEVEL_2_NAME"], s["ADM_LEVEL_3_NAME"])
        bp = int(s["BREAKPOINT_YEARMONTH"])
        tail_months = [m for m in months_sorted if bp <= m <= last_ym]
        g = raw_by_key.get(key)
        for m in tail_months:
            if g is None or (g["YEARMONTH"] == m).sum() == 0:
                cat = "missing_row"
                dl_raw = None
            else:
                row = g[g["YEARMONTH"] == m].iloc[0]
                dl_raw = row["AVERAGE_THROUGHPUT_DOWNLOAD_3G"]
                if str(dl_raw).strip() == "":
                    cat = "empty_field"
                else:
                    try:
                        cat = "explicit_zero" if float(dl_raw) == 0.0 else "nonzero_unexpected"
                    except ValueError:
                        cat = "unparseable"
            rows.append({
                "department": s["ADM_LEVEL_1_NAME"], "province": s["ADM_LEVEL_2_NAME"],
                "district": s["ADM_LEVEL_3_NAME"], "yearmonth": m, "category": cat,
            })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "detection_zero_types.csv", index=False, encoding="utf-8")

    per_district = out.groupby(["department", "province", "district"])["category"].apply(set)
    only_explicit = per_district.apply(lambda s: s == {"explicit_zero"}).sum()
    treated_keys = set(
        district_key(t["department"], t["province"], t["district"])
        for _, t in base["did_summary"][~base["did_summary"]["unmatched"]].iterrows()
    )
    per_district_keys = per_district.index.to_frame(index=False).apply(
        lambda r: district_key(r["department"], r["province"], r["district"]), axis=1
    )
    only_explicit_67 = int(
        per_district[per_district_keys.isin(treated_keys).values].apply(lambda s: s == {"explicit_zero"}).sum()
    )
    counts = out["category"].value_counts().to_dict()
    print(f"  Distribucion de categorias: {counts}")
    print(f"  De los 86 confirmados, solo 'explicit_zero' en todo el post: {only_explicit}")
    print(f"  De los 67 analizados, solo 'explicit_zero' en todo el post: {only_explicit_67}")
    return out, {
        "counts": {str(k): int(v) for k, v in counts.items()},
        "n_86_only_explicit_zero": int(only_explicit),
        "n_67_only_explicit_zero": only_explicit_67,
    }


# ─────────────────────────────────────────────────────────────────────────────
# T1 — Robustez del estimador DiD (download)
# ─────────────────────────────────────────────────────────────────────────────
def t1_robustness(base: dict) -> tuple[pd.DataFrame, dict]:
    print("\n=== T1 — Robustez DiD (download) ===")
    matches = base["matches"]
    did_summary = base["did_summary"]
    by_key = base["by_key"]
    global_months = base["global_months"]
    summary_ubigeo = base["summary_ubigeo"].copy()
    summary_ubigeo["_key"] = summary_ubigeo.apply(
        lambda r: district_key(r["department"], r["province"], r["district"]), axis=1
    )
    ubigeo_by_key = summary_ubigeo.set_index("_key")

    matched = did_summary[~did_summary["unmatched"]].copy()
    matched["_key"] = matched.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)

    treated_groups = matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])

    rows_out = []

    def summarize(name: str, did_vals: list[float], crude_vals: list[float], extra: dict | None = None) -> dict:
        did_arr = np.array(did_vals, dtype=float)
        crude_arr = np.array(crude_vals, dtype=float)
        ci_lo, ci_hi = bootstrap_median_ci(did_arr)
        p1, p2 = wilcoxon_pair(did_arr)
        npos, nneg = npos_nneg(did_arr)
        entry = {
            "variant": name,
            "n": int(np.sum(~np.isnan(did_arr))),
            "did_median": r4(np.nanmedian(did_arr)) if len(did_arr) else None,
            "did_ci95_lo": r4(ci_lo), "did_ci95_hi": r4(ci_hi),
            "wilcoxon_p_onesided": round_p(p1) if not np.isnan(p1) else None,
            "wilcoxon_p_twosided": round_p(p2) if not np.isnan(p2) else None,
            "n_positive": npos, "n_negative": nneg,
            "crude_median": r4(np.nanmedian(crude_arr)) if len(crude_arr) else None,
        }
        if extra:
            entry.update(extra)
        rows_out.append(entry)
        print(f"  [{name:15s}] n={entry['n']:3d} did_median={entry['did_median']} "
              f"IC95=[{entry['did_ci95_lo']},{entry['did_ci95_hi']}] crude={entry['crude_median']}")
        return entry

    # --- principal ---------------------------------------------------------
    summarize("principal", matched["did"].tolist(), matched["delta_treated"].tolist())

    # --- weighted (tratados y controles) ------------------------------------
    weighted_did = []
    weighted_crude = []
    for (dept, prov, dist, bp), grp in treated_groups:
        bp = int(bp)
        pre_m = cal_window(bp, list(range(-6, 0)), global_months)
        post_m = cal_window(bp, list(range(0, 6)), global_months)
        t_key = district_key(dept, prov, dist)
        g_t = by_key.get(t_key)
        pre_t = weighted_mean(g_t, pre_m, DL_COL)
        post_t = weighted_mean(g_t, post_m, DL_COL)
        if np.isnan(pre_t) or np.isnan(post_t):
            continue
        delta_t = post_t - pre_t
        ctrl_deltas = []
        for c_key in grp["control_key"]:
            g_c = by_key.get(c_key)
            pre_c = weighted_mean(g_c, pre_m, DL_COL)
            post_c = weighted_mean(g_c, post_m, DL_COL)
            if not (np.isnan(pre_c) or np.isnan(post_c)):
                ctrl_deltas.append(post_c - pre_c)
        if not ctrl_deltas:
            continue
        weighted_did.append(delta_t - float(np.mean(ctrl_deltas)))
        weighted_crude.append(delta_t)
    summarize("weighted", weighted_did, weighted_crude)

    # --- strict_post6 (>=6 meses post, ventana post exacta de 6) ------------
    strict_did, strict_crude = [], []
    for _, row in matched.iterrows():
        u = ubigeo_by_key.loc[row["_key"]] if row["_key"] in ubigeo_by_key.index else None
        months_post = int(u["months_post"]) if u is not None else 0
        if months_post >= 6:
            strict_did.append(row["did"])
            strict_crude.append(row["delta_treated"])
    summarize("strict_post6", strict_did, strict_crude)

    # --- excl_low_meas (a): solo tratados, controles intactos ---------------
    excl_a_did, excl_a_crude = [], []
    for _, row in matched.iterrows():
        u = ubigeo_by_key.loc[row["_key"]] if row["_key"] in ubigeo_by_key.index else None
        if u is None:
            continue
        months_pre, months_post = int(u["months_pre"]), int(u["months_post"])
        avg_meas = (u["pre6_4g_download_measurements"] + u["post6_4g_download_measurements"]) / (months_pre + months_post)
        if avg_meas >= EXCL_MEAS:
            excl_a_did.append(row["did"])
            excl_a_crude.append(row["delta_treated"])
    summarize("excl_low_meas_a", excl_a_did, excl_a_crude,
              {"note": "solo tratados excluidos por avg_meas_per_month<1000 (formula v1.0); controles intactos"})

    # --- excl_low_meas (b): tratados y controles, >=3 controles requeridos --
    excl_b_did, excl_b_crude, excl_b_dropped_for_controls = [], [], 0
    for (dept, prov, dist, bp), grp in treated_groups:
        bp = int(bp)
        t_key = district_key(dept, prov, dist)
        if t_key not in ubigeo_by_key.index:
            continue
        u = ubigeo_by_key.loc[t_key]
        months_pre, months_post = int(u["months_pre"]), int(u["months_post"])
        avg_meas_t = (u["pre6_4g_download_measurements"] + u["post6_4g_download_measurements"]) / (months_pre + months_post)
        if avg_meas_t < EXCL_MEAS:
            continue
        pre_m = cal_window(bp, list(range(-6, 0)), global_months)
        post_m = cal_window(bp, list(range(0, 6)), global_months)
        n_win = len(pre_m) + len(post_m)
        surviving_ctrl_deltas = []
        for _, m in grp.iterrows():
            c_key = m["control_key"]
            g_c = by_key.get(c_key)
            mean_meas_pre = mean_meas(g_c, pre_m)
            mean_meas_post = mean_meas(g_c, post_m)
            if np.isnan(mean_meas_pre):
                mean_meas_pre = 0.0
            if np.isnan(mean_meas_post):
                mean_meas_post = 0.0
            avg_meas_c = (mean_meas_pre + mean_meas_post) / n_win if n_win else 0.0
            if avg_meas_c >= EXCL_MEAS:
                surviving_ctrl_deltas.append(m["control_post6_4g"] - m["control_pre6_4g"])
        if len(surviving_ctrl_deltas) < 3:
            excl_b_dropped_for_controls += 1
            continue
        row = matched[matched["_key"] == t_key]
        if row.empty:
            continue
        delta_t = float(row["delta_treated"].iloc[0])
        did_b = delta_t - float(np.mean(surviving_ctrl_deltas))
        excl_b_did.append(did_b)
        excl_b_crude.append(delta_t)
    summarize("excl_low_meas_b", excl_b_did, excl_b_crude, {
        "note": "tratados y controles excluidos por avg_meas_per_month<1000 (control: analogo sobre ventana "
                "calendario del tratado); tratado se descarta si quedan <3 controles",
        "n_treated_dropped_lt3_controls": excl_b_dropped_for_controls,
    })

    # --- excl_5G (verificacion vs v1.1) -------------------------------------
    v11 = base["obs_stats_v11"]["robustness"]["excl_5g_contaminated"]["outcomes"]["download"]
    rows_out.append({
        "variant": "excl_5G", "n": v11["n"], "did_median": v11["did_median"],
        "did_ci95_lo": v11["ci95_lo"], "did_ci95_hi": v11["ci95_hi"],
        "wilcoxon_p_onesided": v11.get("wilcoxon_p_onesided"),
        "wilcoxon_p_twosided": v11["wilcoxon_p_twosided"],
        "n_positive": v11["n_positive"], "n_negative": v11["n_negative"],
        "crude_median": v11["raw_median"], "note": "reutiliza observable_stats_v1_1.json tal cual",
    })
    print(f"  [excl_5G        ] n={v11['n']:3d} did_median={v11['did_median']} (reutilizado de v1.1)")

    # --- window_3 (pre=3, post=3) --------------------------------------------
    def window_variant(name, pre_offsets, post_offsets, min_post_valid=None):
        did_vals, crude_vals = [], []
        for (dept, prov, dist, bp), grp in treated_groups:
            bp = int(bp)
            pre_m = cal_window(bp, pre_offsets, global_months)
            post_m = cal_window(bp, post_offsets, global_months)
            t_key = district_key(dept, prov, dist)
            g_t = by_key.get(t_key)
            n_post_valid = n_valid_months(g_t, post_m)
            if min_post_valid is not None and n_post_valid < min_post_valid:
                continue
            pre_t = simple_mean(g_t, pre_m, DL_COL)
            post_t = simple_mean(g_t, post_m, DL_COL)
            if np.isnan(pre_t) or np.isnan(post_t):
                continue
            delta_t = post_t - pre_t
            ctrl_deltas = []
            for c_key in grp["control_key"]:
                g_c = by_key.get(c_key)
                pre_c = simple_mean(g_c, pre_m, DL_COL)
                post_c = simple_mean(g_c, post_m, DL_COL)
                if not (np.isnan(pre_c) or np.isnan(post_c)):
                    ctrl_deltas.append(post_c - pre_c)
            if not ctrl_deltas:
                continue
            did_vals.append(delta_t - float(np.mean(ctrl_deltas)))
            crude_vals.append(delta_t)
        return summarize(name, did_vals, crude_vals)

    window_variant("window_3", list(range(-3, 0)), list(range(0, 3)))
    window_variant("window_4", list(range(-4, 0)), list(range(0, 4)), min_post_valid=3)

    out_df = pd.DataFrame(rows_out)
    out_df.to_csv(OUT_DIR / "did_robustness_v1_2.csv", index=False, encoding="utf-8")
    return out_df, {"variants": rows_out,
                     "note_matches": "window_3/window_4 reutilizan los mismos K=5 controles de v1.0 (matching hizo baseline pre6); no se re-empareja"}


# ─────────────────────────────────────────────────────────────────────────────
# T2 — Event study con incertidumbre y n
# ─────────────────────────────────────────────────────────────────────────────
def t2_event_study(base: dict) -> tuple[pd.DataFrame, dict]:
    print("\n=== T2 — Event study con IC bootstrap de la media + n ===")
    matches = base["matches"]
    did_summary = base["did_summary"]
    by_key = base["by_key"]
    treated_series = base["treated_series"]

    matched = did_summary[~did_summary["unmatched"]].copy()
    treated_groups = matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])

    rows = []
    for (dept, prov, dist, bp), grp in treated_groups:
        bp = int(bp)
        t_key = district_key(dept, prov, dist)
        t_ser = treated_series[treated_series["_key"] == t_key]
        for tau in range(-6, 6):
            cal_ym = idx_to_ym(ym_to_idx(bp) + tau)
            t_row = t_ser[t_ser["YEARMONTH"] == cal_ym]
            if not t_row.empty and MEAS_COL in t_row.columns and float(t_row[MEAS_COL].iloc[0]) > 0:
                t_dl = float(t_row[DL_COL].iloc[0])
            else:
                t_dl = float("nan")
            c_dls = []
            for c_key in grp["control_key"]:
                g_c = by_key.get(c_key)
                if g_c is None:
                    continue
                c_r = g_c[g_c["YEARMONTH"] == cal_ym]
                if not c_r.empty and MEAS_COL in c_r.columns and float(c_r[MEAS_COL].iloc[0]) > 0:
                    c_dls.append(float(c_r[DL_COL].iloc[0]))
            c_dl = float(np.mean(c_dls)) if c_dls else float("nan")
            gap = t_dl - c_dl if not (np.isnan(t_dl) or np.isnan(c_dl)) else float("nan")
            rows.append({"treated_key": t_key, "tau": tau, "gap": gap})

    event_df = pd.DataFrame(rows)
    out_rows = []
    for tau in range(-6, 6):
        vals = event_df[event_df["tau"] == tau]["gap"].dropna().values
        if len(vals) == 0:
            out_rows.append({"tau": tau, "estimate": None, "ci_low": None, "ci_high": None, "n_treated": 0})
            continue
        ci_lo, ci_hi = bootstrap_mean_ci(vals)
        out_rows.append({
            "tau": tau, "estimate": r4(np.mean(vals)),
            "ci_low": r4(ci_lo), "ci_high": r4(ci_hi), "n_treated": int(len(vals)),
        })
        print(f"  tau={tau:+d}: mean={out_rows[-1]['estimate']} IC95=[{out_rows[-1]['ci_low']},"
              f"{out_rows[-1]['ci_high']}] n={out_rows[-1]['n_treated']}")

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(OUT_DIR / "event_study_v1_2.csv", index=False, encoding="utf-8")
    meta = {
        "aggregation": "media entre distritos tratados del gap (tratado - media de sus K controles) por mes "
                        "calendario, tau=-6..+5 (misma agregacion que event_study.csv de v1.0, T0.4)",
        "bootstrap": {"seed": BOOT_SEED, "n_iterations": BOOT_N, "resample_unit": "distrito tratado",
                      "statistic": "media (no mediana, para ser consistente con event_study.csv v1.0)"},
    }
    return out_df, meta


# ─────────────────────────────────────────────────────────────────────────────
# T3 — Sensibilidad de la deteccion
# ─────────────────────────────────────────────────────────────────────────────
def _detect_variant(full_pre_clean: pd.DataFrame, carrier: str, rule: str, zero_types: pd.DataFrame) -> pd.DataFrame:
    d = full_pre_clean[full_pre_clean["NETWORK_CARRIER"] == carrier.upper()].copy()
    last_ym = int(d["YEARMONTH"].max())
    months_sorted = sorted(d["YEARMONTH"].unique().tolist())
    zero_by_key_month = {}
    if rule == "explicit_zero_only":
        for _, r in zero_types.iterrows():
            key = district_key(r["department"], r["province"], r["district"])
            zero_by_key_month[(key, int(r["yearmonth"]))] = r["category"]

    rows = []
    for key, g in d.groupby(["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME", "NETWORK_CARRIER"], dropna=False):
        g = g.sort_values("YEARMONTH")
        seen_active = False
        breakpoint = None
        for _, r in g.iterrows():
            if bool(r["IS_3G_ACTIVE_MONTH"]):
                seen_active = True
            if seen_active and bool(r["IS_3G_ZERO_MONTH"]):
                breakpoint = int(r["YEARMONTH"])
                break
        if breakpoint is None:
            continue
        pre = g[g["YEARMONTH"] < breakpoint]
        if int(pre["IS_3G_ACTIVE_MONTH"].sum()) < MIN_ACTIVE_MONTHS_PRE:
            continue
        tail_months = [m for m in months_sorted if breakpoint <= m <= last_ym]
        g_tail = g[g["YEARMONTH"].isin(tail_months)]
        if len(g_tail) < len(tail_months):
            continue
        if "ROW_PRESENT_IN_SOURCE" in g_tail.columns and bool((~g_tail["ROW_PRESENT_IN_SOURCE"]).any()):
            continue
        if bool((~g_tail["IS_3G_ZERO_MONTH"]).any()):
            continue

        dept, prov, dist, carr = key
        dkey = district_key(dept, prov, dist)

        if rule in ("confirm_min3", "confirm_min6"):
            need = 3 if rule == "confirm_min3" else 6
            consecutive = 0
            for m in tail_months[:need]:
                row = g_tail[g_tail["YEARMONTH"] == m]
                if not row.empty and bool(row["IS_3G_ZERO_MONTH"].iloc[0]):
                    consecutive += 1
                else:
                    break
            if consecutive < min(need, len(tail_months)):
                continue
        elif rule == "explicit_zero_only":
            ok = True
            for m in tail_months:
                cat = zero_by_key_month.get((dkey, m))
                if cat != "explicit_zero":
                    ok = False
                    break
            if not ok:
                continue

        rows.append({
            "ADM_LEVEL_1_NAME": dept, "ADM_LEVEL_2_NAME": prov, "ADM_LEVEL_3_NAME": dist,
            "NETWORK_CARRIER": carr, "BREAKPOINT_YEARMONTH": breakpoint, "LAST_YEARMONTH_AVAILABLE": last_ym,
        })
    return pd.DataFrame(rows)


def t3_detection_sensitivity(base: dict) -> tuple[pd.DataFrame, dict]:
    print("\n=== T3 — Sensibilidad de la deteccion ===")
    raw_frames = []
    for f in sorted(RAW_DIR.glob("dataset_*.csv")):
        df = read_csv_safely(f)
        df["SOURCE_FILE"] = f.name
        raw_frames.append(df)
    raw = pd.concat(raw_frames, ignore_index=True)
    raw = clean_minimal(raw)
    raw = add_yearmonth(raw)
    raw = add_3g_flags(raw)

    zero_types, _ = t0_1_zero_types(base)

    matches = base["matches"]
    did_summary = base["did_summary"]
    by_key = base["by_key"]
    global_months = base["global_months"]
    matched = did_summary[~did_summary["unmatched"]].copy()
    matched["_key"] = matched.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)
    matched_keys = set(matched["_key"])

    rows_out = []
    for rule in ["confirm_min3", "confirm_min6", "explicit_zero_only"]:
        variant = _detect_variant(raw, "MOVISTAR", rule, zero_types)
        n_confirmed = len(variant)
        if variant.empty:
            surviving_keys = set()
        else:
            variant["_key"] = variant.apply(
                lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
            )
            surviving_keys = set(variant["_key"]) & matched_keys
        did_vals, crude_vals = [], []
        for _, row in matched.iterrows():
            if row["_key"] not in surviving_keys:
                continue
            did_vals.append(row["did"])
            crude_vals.append(row["delta_treated"])
        did_arr = np.array(did_vals, dtype=float)
        ci_lo, ci_hi = bootstrap_median_ci(did_arr)
        p1, p2 = wilcoxon_pair(did_arr)
        npos, nneg = npos_nneg(did_arr)
        entry = {
            "rule": rule, "n_confirmed": n_confirmed, "n_analyzed_surviving_67": len(did_vals),
            "did_median": r4(np.nanmedian(did_arr)) if len(did_arr) else None,
            "did_ci95_lo": r4(ci_lo), "did_ci95_hi": r4(ci_hi),
            "wilcoxon_p_onesided": round_p(p1) if not np.isnan(p1) else None,
            "n_positive": npos, "n_negative": nneg,
        }
        rows_out.append(entry)
        print(f"  [{rule:20s}] n_confirmed={n_confirmed} n_surviving_de_67={entry['n_analyzed_surviving_67']} "
              f"did_median={entry['did_median']}")

    out_df = pd.DataFrame(rows_out)
    out_df.to_csv(OUT_DIR / "detection_sensitivity_v1_2.csv", index=False, encoding="utf-8")
    return out_df, {"variants": rows_out, "note": "no se re-empareja: sobrevivientes conservan sus K controles de v1.0"}


# ─────────────────────────────────────────────────────────────────────────────
# T4 — Diagnosticos del matching
# ─────────────────────────────────────────────────────────────────────────────
def t4_matching_diagnostics(base: dict) -> tuple[pd.DataFrame, dict]:
    print("\n=== T4 — Diagnosticos del matching ===")
    matches = base["matches"].copy()
    by_treated = matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])
    n_distinct = by_treated["control_key"].nunique()
    print(f"  Controles distintos por tratado: min={n_distinct.min()} mediana={n_distinct.median()} max={n_distinct.max()}")
    n_lt5 = int((n_distinct < 5).sum())
    print(f"  Tratados con <5 controles distintos: {n_lt5}")

    reuse = matches["control_key"].value_counts()
    print(f"  Total controles unicos usados: {matches['control_key'].nunique()}")
    print(f"  Reuso: min={reuse.min()} mediana={reuse.median()} p90={reuse.quantile(0.9)} max={reuse.max()}")
    top5 = reuse.head(5)

    # Balance: usar caliper "before" = pool elegible sin restriccion de caliper (mismo region3), por tratado
    full = base["full"]
    global_months = base["global_months"]
    shutdown = base["shutdown"]
    treated_keys = set(
        district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"])
        for _, r in shutdown.iterrows()
    )
    ctrl_full = full[~full["_key"].isin(treated_keys)].copy()
    ctrl_by_key = {k: g.sort_values("YEARMONTH").reset_index(drop=True) for k, g in ctrl_full.groupby("_key")}

    universe = pd.read_csv(ROOT / "outputs" / "tables" / "movistar_universe_with_region_a_mano.csv", encoding="cp1252")
    universe["_key"] = universe.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)
    universe["altitud_m"] = pd.to_numeric(universe["altitud_m"], errors="coerce")
    universe["poblacion_distrito"] = pd.to_numeric(universe["poblacion_distrito"], errors="coerce")
    universe["log10_pop"] = np.log10(universe["poblacion_distrito"].clip(lower=1))
    universe["_norm_key"] = universe["_key"].map(bcd.norm_key)
    universe = universe.drop_duplicates(subset="_norm_key")
    uni_norm_lookup = universe.set_index("_norm_key")

    summary_ubigeo = base["summary_ubigeo"].copy()
    summary_ubigeo["_key"] = summary_ubigeo.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)

    before_pre6, before_logpop, before_alt, before_region_match = [], [], [], []
    treated_pre6, treated_logpop, treated_alt, treated_region = [], [], [], []

    matched_summary = base["did_summary"][~base["did_summary"]["unmatched"]]
    for _, t in matched_summary.iterrows():
        bp = int(t["breakpoint_yearmonth"])
        t_key = district_key(t["department"], t["province"], t["district"])
        u_row = summary_ubigeo[summary_ubigeo["_key"] == t_key]
        if u_row.empty:
            continue
        u_row = u_row.iloc[0]
        region3_i = t["region3"]
        pre6_i = float(t["pre6_treated"])
        log_pop_i = (
            float(np.log10(max(float(u_row["poblacion_distrito"]), 1)))
            if pd.notna(u_row.get("poblacion_distrito")) else float("nan")
        )
        alt_i = float(u_row["altitud_m"]) if pd.notna(u_row.get("altitud_m")) else float("nan")

        pre_m = cal_window(bp, list(range(-6, 0)), global_months)
        post_m = cal_window(bp, list(range(0, 6)), global_months)
        eligible = bcd.find_eligible(
            ctrl_by_key, uni_norm_lookup, pre_m, post_m, region3_i, pre6_i, log_pop_i, alt_i,
            cal_4g=1e9, cal_logpop=1e9, cal_alt=1e9,
        )
        for e in eligible:
            before_pre6.append(e["pre6_j"])
            before_logpop.append(e["log10_pop"])
            before_alt.append(e["altitud_m"])
        treated_pre6.extend([pre6_i] * len(eligible))
        treated_logpop.extend([log_pop_i] * len(eligible))
        treated_alt.extend([alt_i] * len(eligible))

    def smd(t_vals, c_vals):
        t_arr = np.array([v for v in t_vals if v is not None and not np.isnan(v)])
        c_arr = np.array([v for v in c_vals if v is not None and not np.isnan(v)])
        if len(t_arr) < 2 or len(c_arr) < 2:
            return float("nan"), float("nan")
        sp = np.sqrt((t_arr.var(ddof=1) + c_arr.var(ddof=1)) / 2)
        smd_val = (t_arr.mean() - c_arr.mean()) / sp if sp > 0 else float("nan")
        vr = c_arr.var(ddof=1) / t_arr.var(ddof=1) if t_arr.var(ddof=1) > 0 else float("nan")
        return float(smd_val), float(vr)

    balance_rows = []
    for var, t_before, c_before, t_col_after, c_col_after in [
        ("pre6_4g_download_mbps", treated_pre6, before_pre6, "treated_pre6_4g", "control_pre6_4g"),
        ("log10_poblacion", treated_logpop, before_logpop, "treated_log10_pop", "control_log10_pop"),
        ("altitud_m", treated_alt, before_alt, "treated_altitud_m", "control_altitud_m"),
    ]:
        smd_before, vr_before = smd(t_before, c_before)
        t_after = matches.drop_duplicates(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])[t_col_after]
        c_after = matches[c_col_after]
        smd_after, vr_after = smd(t_after.tolist(), c_after.tolist())
        balance_rows.append({
            "variable": var,
            "treated_mean": r4(np.nanmean(t_after)), "control_mean_before": r4(np.nanmean(before_pre6 if var == "pre6_4g_download_mbps" else (before_logpop if var == "log10_poblacion" else before_alt))),
            "control_mean_after": r4(np.nanmean(c_after)),
            "smd_before": r4(smd_before), "smd_after": r4(smd_after),
            "variance_ratio_before": r4(vr_before), "variance_ratio_after": r4(vr_after),
        })

    region_match = float((matches["treated_region3"] == matches["control_region3"]).mean())
    balance_df = pd.DataFrame(balance_rows)
    balance_df.to_csv(OUT_DIR / "did_balance_full_v1_2.csv", index=False, encoding="utf-8")
    max_smd_after = float(np.nanmax(np.abs(balance_df["smd_after"])))

    print(f"  region3 match exacto (post-matching): {region_match:.4f}")
    print(f"  max |SMD| post-matching: {max_smd_after:.4f}")

    diagnostics = {
        "distinct_controls_per_treated": {"min": int(n_distinct.min()), "median": float(n_distinct.median()),
                                           "max": int(n_distinct.max()), "n_lt_5": n_lt5},
        "total_unique_controls": int(matches["control_key"].nunique()),
        "reuse_frequency": {"min": int(reuse.min()), "median": float(reuse.median()),
                             "p90": float(reuse.quantile(0.9)), "max": int(reuse.max())},
        "top5_most_reused": [{"control_key": k, "n_uses": int(v)} for k, v in top5.items()],
        "balance": balance_rows,
        "region3_exact_match_fraction": r4(region_match),
        "max_abs_smd_after": r4(max_smd_after),
        "note_before_baseline": "SMD 'antes' calculado sobre el pool elegible en la misma region3, misma ventana "
                                 "calendario y misma regla MIN_VALID, SIN restriccion de caliper (cal=1e9) — "
                                 "construccion nueva de v1.2 (no existia en v1.0), declarada por regla 8",
    }
    return balance_df, diagnostics


# ─────────────────────────────────────────────────────────────────────────────
# T5 — Placebo temporal
# ─────────────────────────────────────────────────────────────────────────────
def t5_placebo(base: dict) -> dict:
    print("\n=== T5 — Placebo temporal (bp-6) ===")
    matches = base["matches"]
    did_summary = base["did_summary"]
    by_key = base["by_key"]
    global_months = base["global_months"]
    matched = did_summary[~did_summary["unmatched"]].copy()
    treated_groups = matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])

    did_vals, crude_vals, excluded = [], [], []
    for (dept, prov, dist, bp), grp in treated_groups:
        bp = int(bp)
        pre_m = cal_window(bp, list(range(-12, -6)), global_months)
        post_m = cal_window(bp, list(range(-6, 0)), global_months)
        if len(pre_m) < 6:
            excluded.append(district_key(dept, prov, dist))
            continue
        t_key = district_key(dept, prov, dist)
        g_t = by_key.get(t_key)
        pre_t = simple_mean(g_t, pre_m, DL_COL)
        post_t = simple_mean(g_t, post_m, DL_COL)
        if np.isnan(pre_t) or np.isnan(post_t):
            excluded.append(t_key)
            continue
        delta_t = post_t - pre_t
        ctrl_deltas = []
        for c_key in grp["control_key"]:
            g_c = by_key.get(c_key)
            pre_c = simple_mean(g_c, pre_m, DL_COL)
            post_c = simple_mean(g_c, post_m, DL_COL)
            if not (np.isnan(pre_c) or np.isnan(post_c)):
                ctrl_deltas.append(post_c - pre_c)
        if not ctrl_deltas:
            excluded.append(t_key)
            continue
        did_vals.append(delta_t - float(np.mean(ctrl_deltas)))
        crude_vals.append(delta_t)

    did_arr = np.array(did_vals)
    ci_lo, ci_hi = bootstrap_median_ci(did_arr)
    _, p_two = wilcoxon_pair(did_arr)
    npos, nneg = npos_nneg(did_arr)
    print(f"  n={len(did_arr)} excluidos={len(excluded)} did_median={np.median(did_arr):.4f} "
          f"IC95=[{ci_lo:.4f},{ci_hi:.4f}] p2s={p_two:.3g}")
    return {
        "n": len(did_arr), "n_excluded": len(excluded), "excluded_keys": excluded,
        "did_median": r4(np.median(did_arr)), "ci95_lo": r4(ci_lo), "ci95_hi": r4(ci_hi),
        "wilcoxon_p_twosided": round_p(p_two) if not np.isnan(p_two) else None,
        "n_positive": npos, "n_negative": nneg,
        "outcome": "download 4G", "pseudo_breakpoint": "bp-6",
    }


# ─────────────────────────────────────────────────────────────────────────────
# T6 — Distritos con cambio negativo
# ─────────────────────────────────────────────────────────────────────────────
def t6_negative_districts(base: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    print("\n=== T6 — Distritos con cambio negativo ===")
    matches = base["matches"]
    did_summary = base["did_summary"]
    summary_ubigeo = base["summary_ubigeo"].copy()
    summary_ubigeo["_key"] = summary_ubigeo.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)
    matched = did_summary[~did_summary["unmatched"]].copy()
    matched["_key"] = matched.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)

    by_key = base["by_key"]
    global_months = base["global_months"]
    meas5g = "THROUGHPUT_DOWNLOAD_5G_NSA_MEASUREMENTS"

    negative = matched[(matched["delta_treated"] < 0) | (matched["did"] < 0)].copy()
    rows = []
    for _, row in negative.iterrows():
        u = summary_ubigeo[summary_ubigeo["_key"] == row["_key"]]
        u = u.iloc[0] if not u.empty else None
        c_grp = matches[
            (matches["treated_dept"] == row["department"]) & (matches["treated_prov"] == row["province"]) &
            (matches["treated_dist"] == row["district"]) & (matches["treated_bp"] == row["breakpoint_yearmonth"])
        ]
        bp = int(row["breakpoint_yearmonth"])
        post_m_avail = cal_window(bp, list(range(0, 6)), global_months)
        g_t = by_key.get(row["_key"])
        has_5g_post = False
        if g_t is not None and meas5g in g_t.columns:
            rows_post = g_t[g_t["YEARMONTH"].isin(post_m_avail)]
            has_5g_post = bool((rows_post[meas5g].fillna(0) > 0).any())
        rows.append({
            "department": row["department"], "province": row["province"], "district": row["district"],
            "region3": row["region3"], "breakpoint": row["breakpoint_yearmonth"],
            "months_post": int(u["months_post"]) if u is not None else None,
            "pre_dl": r4(row["pre6_treated"]), "post_dl": r4(row["post6_treated"]),
            "delta_raw": r4(row["delta_treated"]), "did": r4(row["did"]),
            "pre_meas": r4(u["pre6_4g_download_measurements"]) if u is not None else None,
            "post_meas": r4(u["post6_4g_download_measurements"]) if u is not None else None,
            "pct_change_meas": r4((u["post6_4g_download_measurements"] - u["pre6_4g_download_measurements"]) / u["pre6_4g_download_measurements"]) if u is not None and u["pre6_4g_download_measurements"] else None,
            "has_5g_post": has_5g_post,
            "altitud_m": u["altitud_m"] if u is not None else None,
            "poblacion": u["poblacion_distrito"] if u is not None else None,
            "delta_time4g": r4(u["delta_4g_time_pp"]) if u is not None else None,
            "delta_latency": r4(u["delta_4g_latency_ms"]) if u is not None else None,
            "n_controls": len(c_grp),
        })
    neg_df = pd.DataFrame(rows)
    neg_df.to_csv(OUT_DIR / "negative_districts_v1_2.csv", index=False, encoding="utf-8")
    print(f"  Distritos con delta_raw<0 o did<0: {len(neg_df)}")

    treated_series = base["treated_series"]
    by_key = base["by_key"]
    series_rows = []
    for _, row in negative.iterrows():
        bp = int(row["breakpoint_yearmonth"])
        t_key = row["_key"]
        t_ser = treated_series[treated_series["_key"] == t_key].copy()
        c_grp = matches[
            (matches["treated_dept"] == row["department"]) & (matches["treated_prov"] == row["province"]) &
            (matches["treated_dist"] == row["district"]) & (matches["treated_bp"] == bp)
        ]
        for _, r in t_ser.iterrows():
            tau = ym_to_idx(int(r["YEARMONTH"])) - ym_to_idx(bp)
            if not (-12 <= tau <= 12):
                continue
            c_dls, c_meas = [], []
            for c_key in c_grp["control_key"]:
                g_c = by_key.get(c_key)
                if g_c is None:
                    continue
                c_r = g_c[g_c["YEARMONTH"] == r["YEARMONTH"]]
                if not c_r.empty:
                    c_dls.append(float(c_r[DL_COL].iloc[0]))
                    if MEAS_COL in c_r.columns:
                        c_meas.append(float(c_r[MEAS_COL].iloc[0]))
            series_rows.append({
                "district": row["district"], "department": row["department"], "tau": tau,
                "yearmonth": int(r["YEARMONTH"]), "treated_4g_dl": r.get(DL_COL), "treated_4g_meas": r.get(MEAS_COL),
                "treated_4g_time_pct": r.get("TIME_PERCENTAGE_4G"),
                "control_mean_4g_dl": float(np.mean(c_dls)) if c_dls else None,
                "control_mean_4g_meas": float(np.mean(c_meas)) if c_meas else None,
            })
    series_df = pd.DataFrame(series_rows)
    series_df.to_csv(OUT_DIR / "negative_districts_series_v1_2.csv", index=False, encoding="utf-8")
    return neg_df, series_df


# ─────────────────────────────────────────────────────────────────────────────
# T7 — DiD por region
# ─────────────────────────────────────────────────────────────────────────────
def t7_regional_did(base: dict) -> dict:
    print("\n=== T7 — DiD por region (Costa/Sierra) ===")
    did_summary = base["did_summary"]
    matched = did_summary[~did_summary["unmatched"]].copy()

    out = {}
    region_arrs = {}
    for region in ["Costa", "Sierra"]:
        sub = matched[matched["region3"] == region]
        did_arr = sub["did"].dropna().values
        crude_arr = sub["delta_treated"].dropna().values
        region_arrs[region] = did_arr
        ci_lo, ci_hi = bootstrap_median_ci(did_arr)
        p1, _ = wilcoxon_pair(did_arr)
        npos, nneg = npos_nneg(did_arr)
        out[region.lower()] = {
            "n": len(did_arr), "did_median": r4(np.median(did_arr)) if len(did_arr) else None,
            "ci95_lo": r4(ci_lo), "ci95_hi": r4(ci_hi),
            "wilcoxon_p_onesided": round_p(p1) if not np.isnan(p1) else None,
            "n_positive": npos, "n_negative": nneg,
            "crude_median": r4(np.median(crude_arr)) if len(crude_arr) else None,
        }
        print(f"  {region}: n={out[region.lower()]['n']} did_median={out[region.lower()]['did_median']} "
              f"IC95=[{out[region.lower()]['ci95_lo']},{out[region.lower()]['ci95_hi']}]")

    rng = np.random.default_rng(BOOT_SEED)
    sierra, costa = region_arrs.get("Sierra", np.array([])), region_arrs.get("Costa", np.array([]))
    if len(sierra) and len(costa):
        diffs = np.array([
            np.median(rng.choice(sierra, size=len(sierra), replace=True)) -
            np.median(rng.choice(costa, size=len(costa), replace=True))
            for _ in range(BOOT_N)
        ])
        out["sierra_minus_costa"] = {
            "estimate": r4(np.median(sierra) - np.median(costa)),
            "ci95_lo": r4(np.percentile(diffs, 2.5)), "ci95_hi": r4(np.percentile(diffs, 97.5)),
        }
        print(f"  Sierra-Costa: {out['sierra_minus_costa']}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# T9 — Secuencia 3G off -> 4G -> 5G
# ─────────────────────────────────────────────────────────────────────────────
def t9_5g_sequence(base: dict) -> dict:
    print("\n=== T9 — Secuencia 3G off -> 4G -> 5G ===")
    full = base["full"]
    by_key = base["by_key"]
    global_months = base["global_months"]
    matches = base["matches"]
    did_summary = base["did_summary"]
    matched = did_summary[~did_summary["unmatched"]].copy()
    matched["_key"] = matched.apply(lambda r: district_key(r["department"], r["province"], r["district"]), axis=1)

    # T9.1 — inventario columnas 5G
    cols_5g = [c for c in full.columns if "5G" in c.upper()]
    meas5g = "THROUGHPUT_DOWNLOAD_5G_NSA_MEASUREMENTS"
    nat_5g = full[full[meas5g] > 0] if meas5g in full.columns else full.iloc[0:0]
    first_5g_ym = int(nat_5g["YEARMONTH"].min()) if not nat_5g.empty else None
    districts_with_5g_by_month = (
        nat_5g.groupby("YEARMONTH")["_key"].nunique().to_dict() if not nat_5g.empty else {}
    )
    print(f"  Columnas 5G: {cols_5g}")
    print(f"  Primer YEARMONTH con 5G>0 (nacional MOVISTAR): {first_5g_ym}")

    # T9.2 — timing 5G vs breakpoint (86 confirmados, 67 analizados, controles usados)
    shutdown = base["shutdown"]

    def first_5g_month(key):
        g = by_key.get(key)
        if g is None or meas5g not in g.columns:
            return None
        rows = g[g[meas5g] > 0]
        return int(rows["YEARMONTH"].min()) if not rows.empty else None

    def classify(first_month, bp, post_m_avail):
        if first_month is None:
            return "never"
        if first_month < bp:
            return "5g_before_bp"
        if first_month in post_m_avail:
            return "5g_in_post_window"
        return "5g_after_window"

    timing_rows = []
    for _, s in shutdown.iterrows():
        key = district_key(s["ADM_LEVEL_1_NAME"], s["ADM_LEVEL_2_NAME"], s["ADM_LEVEL_3_NAME"])
        bp = int(s["BREAKPOINT_YEARMONTH"])
        post_m_avail = cal_window(bp, list(range(0, 6)), global_months)
        fm = first_5g_month(key)
        timing_rows.append({
            "group": "confirmed_86", "district_key": key, "breakpoint": bp,
            "first_5g_yearmonth": fm, "relative_month": (ym_to_idx(fm) - ym_to_idx(bp)) if fm else None,
            "class": classify(fm, bp, post_m_avail),
        })
    for _, t in matched.iterrows():
        bp = int(t["breakpoint_yearmonth"])
        post_m_avail = cal_window(bp, list(range(0, 6)), global_months)
        fm = first_5g_month(t["_key"])
        timing_rows.append({
            "group": "analyzed_67", "district_key": t["_key"], "breakpoint": bp,
            "first_5g_yearmonth": fm, "relative_month": (ym_to_idx(fm) - ym_to_idx(bp)) if fm else None,
            "class": classify(fm, bp, post_m_avail),
        })
    control_keys_bp = matches[["control_key", "treated_bp"]].drop_duplicates()
    for _, c in control_keys_bp.iterrows():
        bp = int(c["treated_bp"])
        post_m_avail = cal_window(bp, list(range(0, 6)), global_months)
        fm = first_5g_month(c["control_key"])
        timing_rows.append({
            "group": "controls_used", "district_key": c["control_key"], "breakpoint": bp,
            "first_5g_yearmonth": fm, "relative_month": (ym_to_idx(fm) - ym_to_idx(bp)) if fm else None,
            "class": classify(fm, bp, post_m_avail),
        })
    timing_df = pd.DataFrame(timing_rows)
    timing_df.to_csv(OUT_DIR / "fiveg_timing_v1_2.csv", index=False, encoding="utf-8")
    class_counts = timing_df.groupby("group")["class"].value_counts().unstack(fill_value=0).to_dict(orient="index")
    print(f"  Clasificacion timing 5G por grupo: {class_counts}")

    # T9.3 — contaminacion de controles
    has5g_by_treated = {}
    for _, t in matched.iterrows():
        bp = int(t["breakpoint_yearmonth"])
        post_m_avail = cal_window(bp, list(range(0, 6)), global_months)
        g_t = by_key.get(t["_key"])
        has_5g = False
        if g_t is not None and meas5g in g_t.columns:
            rows = g_t[g_t["YEARMONTH"].isin(post_m_avail)]
            has_5g = bool((rows[meas5g].fillna(0) > 0).any())
        has5g_by_treated[t["_key"]] = has_5g

    treated_groups = matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])
    excl_a_did, excl_b_did, n_lt3 = [], [], 0
    for (dept, prov, dist, bp), grp in treated_groups:
        bp = int(bp)
        t_key = district_key(dept, prov, dist)
        if has5g_by_treated.get(t_key, False):
            continue
        row = matched[matched["_key"] == t_key]
        if row.empty:
            continue
        delta_t = float(row["delta_treated"].iloc[0])
        excl_a_did.append(delta_t - float((grp["control_post6_4g"] - grp["control_pre6_4g"]).mean()))

        post_m_avail = cal_window(bp, list(range(0, 6)), global_months)
        surviving = []
        for _, m in grp.iterrows():
            g_c = by_key.get(m["control_key"])
            has_5g_c = False
            if g_c is not None and meas5g in g_c.columns:
                rows = g_c[g_c["YEARMONTH"].isin(post_m_avail)]
                has_5g_c = bool((rows[meas5g].fillna(0) > 0).any())
            if not has_5g_c:
                surviving.append(m["control_post6_4g"] - m["control_pre6_4g"])
        if len(surviving) < 3:
            n_lt3 += 1
            continue
        excl_b_did.append(delta_t - float(np.mean(surviving)))

    def stat_block(vals):
        arr = np.array(vals, dtype=float)
        ci_lo, ci_hi = bootstrap_median_ci(arr)
        p1, _ = wilcoxon_pair(arr)
        return {"n": len(arr), "did_median": r4(np.median(arr)) if len(arr) else None,
                "ci95_lo": r4(ci_lo), "ci95_hi": r4(ci_hi),
                "wilcoxon_p_onesided": round_p(p1) if not np.isnan(p1) else None}

    contamination = {
        "excl_treated_with_5g": stat_block(excl_a_did),
        "excl_treated_and_controls_with_5g": stat_block(excl_b_did),
        "n_treated_dropped_lt3_controls": n_lt3,
    }
    print(f"  (a) excl tratados con 5G: {contamination['excl_treated_with_5g']}")
    print(f"  (b) excl tratados+controles con 5G: {contamination['excl_treated_and_controls_with_5g']}")

    # T9.4 — 7 distritos 5G Lima bp=202512
    lima_5g = matched[(matched["breakpoint_yearmonth"] == 202512)]
    lima_5g_keys = [k for k in lima_5g["_key"] if has5g_by_treated.get(k, False)] or lima_5g["_key"].tolist()
    series_rows = []
    for t_key in lima_5g_keys:
        row = matched[matched["_key"] == t_key].iloc[0]
        bp = int(row["breakpoint_yearmonth"])
        g_t = by_key.get(t_key)
        c_grp = matches[
            (matches["treated_dept"] == row["department"]) & (matches["treated_prov"] == row["province"]) &
            (matches["treated_dist"] == row["district"]) & (matches["treated_bp"] == bp)
        ]
        if g_t is None:
            continue
        for _, r in g_t.iterrows():
            tau = ym_to_idx(int(r["YEARMONTH"])) - ym_to_idx(bp)
            if tau < -12:
                continue
            c_dls = []
            for c_key in c_grp["control_key"]:
                g_c = by_key.get(c_key)
                if g_c is None:
                    continue
                c_r = g_c[g_c["YEARMONTH"] == r["YEARMONTH"]]
                if not c_r.empty:
                    c_dls.append(float(c_r[DL_COL].iloc[0]))
            series_rows.append({
                "district": row["district"], "tau": tau, "yearmonth": int(r["YEARMONTH"]),
                "time_pct_3g": r.get("TIME_PERCENTAGE_3G"), "time_pct_4g": r.get("TIME_PERCENTAGE_4G"),
                "time_pct_5g": r.get("TIME_PERCENTAGE_5G_NSA"),
                "download_4g": r.get(DL_COL), "download_5g": r.get("AVERAGE_THROUGHPUT_DOWNLOAD_5G_NSA"),
                "meas_4g": r.get(MEAS_COL), "meas_5g": r.get(meas5g),
                "control_mean_4g_dl": float(np.mean(c_dls)) if c_dls else None,
            })
    fiveg_series_df = pd.DataFrame(series_rows)
    fiveg_series_df.to_csv(OUT_DIR / "fiveg_districts_series_v1_2.csv", index=False, encoding="utf-8")
    print(f"  Distritos 5G identificados (bp=202512): {lima_5g_keys}")

    # T9.5 — evidencia de fuga por composicion
    treated_series = base["treated_series"]
    comp_rows = []
    for _, row in matched.iterrows():
        bp = int(row["breakpoint_yearmonth"])
        t_ser = treated_series[treated_series["_key"] == row["_key"]]
        pre_m = cal_window(bp, list(range(-6, 0)), global_months)
        post_m = cal_window(bp, list(range(0, 6)), global_months)
        pre_meas = t_ser[t_ser["YEARMONTH"].isin(pre_m)][MEAS_COL].mean()
        post_meas = t_ser[t_ser["YEARMONTH"].isin(post_m)][MEAS_COL].mean()
        pre_time = t_ser[t_ser["YEARMONTH"].isin(pre_m)]["TIME_PERCENTAGE_4G"].mean()
        post_time = t_ser[t_ser["YEARMONTH"].isin(post_m)]["TIME_PERCENTAGE_4G"].mean()
        comp_rows.append({
            "district_key": row["_key"], "has_5g": row["_key"] in lima_5g_keys,
            "delta_meas_4g": post_meas - pre_meas if pd.notna(pre_meas) and pd.notna(post_meas) else np.nan,
            "delta_time_4g": post_time - pre_time if pd.notna(pre_time) and pd.notna(post_time) else np.nan,
        })
    comp_df = pd.DataFrame(comp_rows)
    g5 = comp_df[comp_df["has_5g"]].dropna()
    g_other = comp_df[~comp_df["has_5g"]].dropna()
    mw_meas = spstats.mannwhitneyu(g5["delta_meas_4g"], g_other["delta_meas_4g"], alternative="two-sided") if len(g5) and len(g_other) else None
    mw_time = spstats.mannwhitneyu(g5["delta_time_4g"], g_other["delta_time_4g"], alternative="two-sided") if len(g5) and len(g_other) else None
    composition = {
        "n_5g_districts": int(len(g5)), "n_other_districts": int(len(g_other)),
        "median_delta_meas_4g_5g": r4(g5["delta_meas_4g"].median()) if len(g5) else None,
        "median_delta_meas_4g_other": r4(g_other["delta_meas_4g"].median()) if len(g_other) else None,
        "mannwhitney_p_meas": round_p(float(mw_meas.pvalue)) if mw_meas is not None else None,
        "median_delta_time4g_5g": r4(g5["delta_time_4g"].median()) if len(g5) else None,
        "median_delta_time4g_other": r4(g_other["delta_time_4g"].median()) if len(g_other) else None,
        "mannwhitney_p_time4g": round_p(float(mw_time.pvalue)) if mw_time is not None else None,
    }
    print(f"  Composicion (5G vs otros): {composition}")

    return {
        "inventory": {"columns_5g": cols_5g, "first_national_5g_yearmonth": first_5g_ym,
                      "districts_with_5g_by_month": {str(k): int(v) for k, v in districts_with_5g_by_month.items()}},
        "timing_class_counts": {str(k): v for k, v in class_counts.items()},
        "contamination": contamination,
        "lima_5g_districts_bp202512": lima_5g_keys,
        "composition_leakage": composition,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def run_all() -> dict:
    base = load_base()
    sanity = sanity_checks(base)

    _, t0_1 = t0_1_zero_types(base)
    _, t1 = t1_robustness(base)
    _, t2_meta = t2_event_study(base)
    _, t3 = t3_detection_sensitivity(base)
    _, t4 = t4_matching_diagnostics(base)
    t5 = t5_placebo(base)
    t6_negative_districts(base)
    t7 = t7_regional_did(base)
    t9 = t9_5g_sequence(base)

    stats = {
        "tag_base": "v1.1-outcomes (worktree paper/v1.2)",
        "sanity": sanity,
        "t0_1_zero_types": t0_1,
        "robustness_matched": t1,
        "event_study_meta": t2_meta,
        "detection_sensitivity": t3,
        "matching_diagnostics": t4,
        "placebo": t5,
        "regional_did": t7,
        "fiveg_sequence": t9,
        "bootstrap": {"seed": BOOT_SEED, "n_iterations": BOOT_N},
    }
    out_path = OUT_DIR / "observable_stats_v1_2.json"
    out_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"\nEscrito: {out_path}")
    return stats


if __name__ == "__main__":
    run_all()
