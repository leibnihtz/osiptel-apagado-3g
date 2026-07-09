#!/usr/bin/env python3
"""
A2 — Diff-in-Diff con grupo de control emparejado (Mahalanobis, K=5, con reemplazo).

Outputs en outputs/tables/:
  did_matches.csv   — pares (tratado, control) con covariables y deltas
  did_summary.csv   — un DiD_i por tratado matcheado
  did_balance.csv   — tabla de balance de covariables pre/post-match
  event_study.csv   — gap(τ) para τ = -6..+5
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portalosiptel3g.cleaning import clean_minimal
from portalosiptel3g.features import add_yearmonth, add_3g_flags

# ── Paths ──────────────────────────────────────────────────────────────────────
RAW_DIR       = ROOT / "data" / "raw"
SHUTDOWN_PATH = ROOT / "outputs" / "tables" / "shutdown_confirmed.csv"
SUMMARY_PATH  = ROOT / "outputs" / "observable" / "data" / "observable_4g_upgrade_summary_with_ubigeo.csv"
UNIVERSE_PATH = ROOT / "outputs" / "tables" / "movistar_universe_with_region_a_mano.csv"
SERIES_PATH   = ROOT / "outputs" / "tables" / "dataset_2023_2026_shutdown_districts.csv"
OUT_DIR       = ROOT / "outputs" / "tables"

# ── Parámetros de matching ─────────────────────────────────────────────────────
K           = 5      # vecinos más cercanos con reemplazo
# Calipers estándar (análisis principal)
CAL_4G      = 1.0   # Mbps — caliper pre6_4g_baseline
CAL_LOGPOP  = 0.5   # en log10(poblacion)
CAL_ALT     = 500.0  # metros
# Calipers relajados (fallback para unmatched — reportar como análisis de sensibilidad)
CAL_4G_R    = 2.0
CAL_LOGPOP_R = 1.0
CAL_ALT_R   = 1000.0
MIN_VALID   = 3      # meses con MEAS > 0 para elegibilidad y análisis

MEAS_COL = "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"
DL_COL   = "AVERAGE_THROUGHPUT_DOWNLOAD_4G"


# ── Utilidades YEARMONTH ───────────────────────────────────────────────────────
def ym_to_idx(ym: int) -> int:
    return (ym // 100) * 12 + (ym % 100) - 1


def idx_to_ym(idx: int) -> int:
    year, month = divmod(idx, 12)
    return year * 100 + month + 1


def window_months(bp: int) -> tuple[list[int], list[int]]:
    """Devuelve 6 meses pre y 6 meses post (en YEARMONTH) alrededor del breakpoint."""
    bp_idx = ym_to_idx(bp)
    pre  = [idx_to_ym(bp_idx - 6 + i) for i in range(6)]
    post = [idx_to_ym(bp_idx + i)      for i in range(6)]
    return pre, post


# ── Funciones de carga ─────────────────────────────────────────────────────────
def load_full_movistar() -> pd.DataFrame:
    dfs = []
    for f in sorted(RAW_DIR.glob("dataset_*.csv")):
        df = pd.read_csv(f, sep=";", dtype=str, encoding="utf-8-sig")
        df["SOURCE_FILE"] = f.name
        dfs.append(df)
    raw = pd.concat(dfs, ignore_index=True)
    raw = clean_minimal(raw)
    raw = add_yearmonth(raw)
    raw = add_3g_flags(raw)
    raw = raw[raw["NETWORK_CARRIER"] == "MOVISTAR"].copy()
    for col in [MEAS_COL, DL_COL, "IS_3G_ACTIVE_MONTH", "IS_3G_ZERO_MONTH"]:
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
    return raw


def district_key(dept: str, prov: str, dist: str) -> str:
    return (
        str(dept).upper().strip() + "|"
        + str(prov).upper().strip() + "|"
        + str(dist).upper().strip()
    )


def _fix_mojibake(s: str) -> str:
    """UTF-8 leído como Latin-1 (Excel abrió sin BOM) → texto correcto."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _norm_part(s: str) -> str:
    s = _fix_mojibake(str(s)).strip().upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("-", " ").replace("_", " ")
    return " ".join(s.split())


def norm_key(raw_key: str) -> str:
    """Convierte 'DEPT|PROV|DIST' a su versión normalizada (sin tildes, guiones, mojibake)."""
    parts = raw_key.split("|", 2)
    return "|".join(_norm_part(p) for p in parts)


def mean_valid_4g(g: pd.DataFrame) -> float:
    rows = g[g[MEAS_COL] > 0] if MEAS_COL in g.columns else g
    if rows.empty or DL_COL not in rows.columns:
        return float("nan")
    return float(rows[DL_COL].mean())


def find_eligible(
    ctrl_by_key: dict,
    uni_norm_lookup: pd.DataFrame,
    pre_m_avail: list,
    post_m_avail: list,
    region3_i: str,
    pre6_i: float,
    log_pop_i: float,
    alt_i: float,
    cal_4g: float,
    cal_logpop: float,
    cal_alt: float,
) -> list[dict]:
    present_win = set(pre_m_avail + post_m_avail)
    eligible = []
    for key, g in ctrl_by_key.items():
        g_win = g[g["YEARMONTH"].isin(present_win)]
        if len(g_win) < len(present_win):
            continue
        if not bool(g_win["IS_3G_ACTIVE_MONTH"].fillna(0).astype(bool).all()):
            continue
        g_pre  = g_win[g_win["YEARMONTH"].isin(pre_m_avail)]
        g_post = g_win[g_win["YEARMONTH"].isin(post_m_avail)]
        pre_ok  = int((g_pre[MEAS_COL]  > 0).sum()) if MEAS_COL in g_pre.columns  else 0
        post_ok = int((g_post[MEAS_COL] > 0).sum()) if MEAS_COL in g_post.columns else 0
        if pre_ok < MIN_VALID or post_ok < MIN_VALID:
            continue
        pre6_j  = mean_valid_4g(g_pre)
        post6_j = mean_valid_4g(g_post)
        if np.isnan(pre6_j) or np.isnan(post6_j):
            continue
        nk = norm_key(key)
        if nk not in uni_norm_lookup.index:
            continue
        u = uni_norm_lookup.loc[nk]
        region3_j = u["region3"] if pd.notna(u.get("region3")) else None
        log_pop_j = float(u["log10_pop"]) if pd.notna(u.get("log10_pop")) else float("nan")
        alt_j     = float(u["altitud_m"]) if pd.notna(u.get("altitud_m")) else float("nan")
        if region3_j != region3_i:
            continue
        if abs(pre6_i - pre6_j) > cal_4g:
            continue
        if not (np.isnan(log_pop_i) or np.isnan(log_pop_j)):
            if abs(log_pop_i - log_pop_j) > cal_logpop:
                continue
        if not (np.isnan(alt_i) or np.isnan(alt_j)):
            if abs(alt_i - alt_j) > cal_alt:
                continue
        eligible.append({
            "key": key,
            "region3": region3_j,
            "pre6_j": pre6_j,
            "post6_j": post6_j,
            "log10_pop": log_pop_j,
            "altitud_m": alt_j,
        })
    return eligible


# ── Matching ───────────────────────────────────────────────────────────────────
def mahal_or_euclidean(treat_vec: np.ndarray, ctrl_mat: np.ndarray) -> np.ndarray:
    t = treat_vec.reshape(1, -1)
    try:
        cov = np.cov(ctrl_mat.T)
        inv_cov = np.linalg.inv(cov)
        return cdist(t, ctrl_mat, metric="mahalanobis", VI=inv_cov)[0]
    except np.linalg.LinAlgError:
        std = ctrl_mat.std(axis=0)
        std[std == 0] = 1.0
        return np.sqrt(((ctrl_mat - t) / std) ** 2).sum(axis=1)


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    print("Cargando dataset completo MOVISTAR...")
    full = load_full_movistar()
    n_districts = full.groupby(["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME"]).ngroups
    print(f"  {len(full):,} filas — {n_districts:,} distritos")

    # Excluir los 86 tratados del pool
    shutdown = pd.read_csv(SHUTDOWN_PATH)
    treated_keys = set(
        district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"])
        for _, r in shutdown.iterrows()
    )
    full["_key"] = full.apply(
        lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
    )
    ctrl_full = full[~full["_key"].isin(treated_keys)].copy()
    print(f"  Pool de control: {ctrl_full['_key'].nunique():,} distritos únicos")

    # Covariables del pool de control (region3, altitud, poblacion)
    universe = pd.read_csv(UNIVERSE_PATH, encoding="cp1252")
    universe["_key"] = universe.apply(
        lambda r: district_key(r["department"], r["province"], r["district"]), axis=1
    )
    universe["altitud_m"]          = pd.to_numeric(universe["altitud_m"], errors="coerce")
    universe["poblacion_distrito"] = pd.to_numeric(universe["poblacion_distrito"], errors="coerce")
    universe["log10_pop"]          = np.log10(universe["poblacion_distrito"].clip(lower=1))
    # Normalizar para tolerar mojibake (ñ→Ã±), tildes y guiones en el CSV manual
    universe["_norm_key"] = universe["_key"].map(norm_key)
    universe = universe.drop_duplicates(subset="_norm_key")
    uni_norm_lookup = universe.set_index("_norm_key")
    n_uni = len(uni_norm_lookup)
    n_with_r3 = uni_norm_lookup["region3"].notna().sum()
    print(f"  Universe (norm-dedup): {n_uni} distritos, {n_with_r3} con region3")

    # Tratados con sus covariables y métricas
    summary = pd.read_csv(SUMMARY_PATH)
    summary["altitud_m"]  = pd.to_numeric(summary["altitud_m"], errors="coerce")
    summary["log10_pop"]  = np.log10(pd.to_numeric(summary["poblacion_distrito"], errors="coerce").clip(lower=1))
    summary = summary[summary["months_post"] >= MIN_VALID].copy()
    print(f"  Tratados con >={MIN_VALID} meses post válidos: {len(summary)}")

    # Pre-agrupar control por key (para eficiencia en el loop)
    ctrl_by_key: dict[str, pd.DataFrame] = {}
    for key, g in ctrl_full.groupby("_key"):
        ctrl_by_key[key] = g.sort_values("YEARMONTH").reset_index(drop=True)

    match_rows: list[dict] = []
    summary_rows: list[dict] = []

    # Meses que existen globalmente (para no penalizar breakpoints recientes con post-window en el futuro)
    global_months = set(int(m) for m in full["YEARMONTH"].dropna().unique())

    print("\nMatching en progreso...")
    for _, t in summary.iterrows():
        bp        = int(t["breakpoint_yearmonth"])
        pre_m, post_m = window_months(bp)
        # Sólo considerar meses que existen en el dataset global
        pre_m_avail  = [m for m in pre_m  if m in global_months]
        post_m_avail = [m for m in post_m if m in global_months]
        present_win  = set(pre_m_avail + post_m_avail)

        region3_i = t.get("region3")
        pre6_i    = float(t["pre6_4g_download_mbps"])
        post6_i   = float(t["post6_4g_download_mbps"])
        log_pop_i = float(t["log10_pop"]) if pd.notna(t["log10_pop"]) else float("nan")
        alt_i     = float(t["altitud_m"]) if pd.notna(t["altitud_m"]) else float("nan")
        t_key     = district_key(t["department"], t["province"], t["district"])

        # Intento 1: calipers estándar
        eligible = find_eligible(
            ctrl_by_key, uni_norm_lookup, pre_m_avail, post_m_avail,
            region3_i, pre6_i, log_pop_i, alt_i,
            CAL_4G, CAL_LOGPOP, CAL_ALT,
        )
        caliper_level = "standard"

        # Fallback: calipers relajados para unmatched
        if len(eligible) < 3:
            eligible_r = find_eligible(
                ctrl_by_key, uni_norm_lookup, pre_m_avail, post_m_avail,
                region3_i, pre6_i, log_pop_i, alt_i,
                CAL_4G_R, CAL_LOGPOP_R, CAL_ALT_R,
            )
            if len(eligible_r) >= 3:
                eligible = eligible_r
                caliper_level = "relaxed"
                print(f"  RELAXED [{len(eligible_r)} elegibles]: {t['district']} ({t['department']}) bp={bp}")
            else:
                caliper_level = "unmatched"

        n_el = len(eligible)
        t_label = f"{t['district']} ({t['department']}) bp={bp}"

        if caliper_level == "unmatched":
            print(f"  UNMATCHED [{n_el} elegibles incluso relajado]: {t_label}")
            summary_rows.append({
                "ubigeo": t.get("ubigeo", ""),
                "department": t["department"], "province": t["province"], "district": t["district"],
                "breakpoint_yearmonth": bp, "region3": region3_i,
                "pre6_treated": pre6_i, "post6_treated": post6_i,
                "delta_treated": post6_i - pre6_i,
                "delta_control_mean": float("nan"), "did": float("nan"),
                "matched_count": n_el, "caliper_level": caliper_level, "unmatched": True,
            })
            continue

        el_df = pd.DataFrame(eligible)
        cov_cols = ["pre6_j", "log10_pop", "altitud_m"]
        el_mat = el_df[cov_cols].copy()
        col_means = el_mat.mean()
        el_mat_filled = el_mat.fillna(col_means)

        t_vec = np.array([
            pre6_i,
            log_pop_i if not np.isnan(log_pop_i) else float(col_means["log10_pop"]),
            alt_i     if not np.isnan(alt_i)     else float(col_means["altitud_m"]),
        ])
        dists = mahal_or_euclidean(t_vec, el_mat_filled.values)

        el_df = el_df.copy()
        el_df["mahal_dist"] = dists
        selected = el_df.nsmallest(K, "mahal_dist")

        delta_treated    = post6_i - pre6_i
        delta_ctrl_mean  = float((selected["post6_j"] - selected["pre6_j"]).mean())
        did              = delta_treated - delta_ctrl_mean

        for _, ctrl in selected.iterrows():
            match_rows.append({
                "treated_ubigeo":    t.get("ubigeo", ""),
                "treated_dept":      t["department"],
                "treated_prov":      t["province"],
                "treated_dist":      t["district"],
                "treated_bp":        bp,
                "treated_region3":   region3_i,
                "treated_pre6_4g":   pre6_i,
                "treated_post6_4g":  post6_i,
                "treated_log10_pop": log_pop_i,
                "treated_altitud_m": alt_i,
                "control_key":       ctrl["key"],
                "control_region3":   ctrl["region3"],
                "control_pre6_4g":   ctrl["pre6_j"],
                "control_post6_4g":  ctrl["post6_j"],
                "control_delta":     ctrl["post6_j"] - ctrl["pre6_j"],
                "control_log10_pop": ctrl["log10_pop"],
                "control_altitud_m": ctrl["altitud_m"],
                "mahal_dist":        ctrl["mahal_dist"],
                "caliper_level":     caliper_level,
            })

        summary_rows.append({
            "ubigeo":             t.get("ubigeo", ""),
            "department":         t["department"],
            "province":           t["province"],
            "district":           t["district"],
            "breakpoint_yearmonth": bp,
            "region3":            region3_i,
            "pre6_treated":       pre6_i,
            "post6_treated":      post6_i,
            "delta_treated":      delta_treated,
            "delta_control_mean": delta_ctrl_mean,
            "did":                did,
            "matched_count":      len(selected),
            "caliper_level":      caliper_level,
            "unmatched":          False,
        })

    matches   = pd.DataFrame(match_rows)
    did_summ  = pd.DataFrame(summary_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    matches.to_csv(OUT_DIR / "did_matches.csv", index=False, encoding="utf-8")
    did_summ.to_csv(OUT_DIR / "did_summary.csv", index=False, encoding="utf-8")

    matched   = did_summ[~did_summ["unmatched"]]
    unmatched = did_summ[did_summ["unmatched"]]
    did_vec   = matched["did"].dropna()

    print(f"\n=== Resultados DiD ===")
    print(f"  Tratados analizados : {len(did_summ)}")
    print(f"  Matcheados          : {len(matched)}")
    print(f"  Sin match (<3 elig) : {len(unmatched)}")
    if not did_vec.empty:
        print(f"  DiD mediana         : {did_vec.median():.4f} Mbps")
        print(f"  DiD media           : {did_vec.mean():.4f} Mbps")
        print(f"  DiD > 0             : {(did_vec > 0).sum()}/{len(did_vec)}")

    # Asserts
    print()
    n_total = len(did_summ)
    n_unm   = len(unmatched)
    print(f"Assert n_total={n_total} == n_analysis: {'OK' if n_total == len(summary) else 'FALLO'}")
    print(f"Assert n_unmatched={n_unm} < 7 (10%): {'OK' if n_unm < 7 else 'REVISAR — relajar calipers'}")
    if not did_vec.empty:
        print(f"Assert DiD mediana > 0: {'OK' if did_vec.median() > 0 else 'PROBLEMA'}")
        print(f"Assert DiD mediana < 0.99: {'OK' if did_vec.median() < 0.99 else 'REVISAR'}")

    # ── Balance table ──────────────────────────────────────────────────────────
    if not matches.empty:
        balance = []
        for var, t_col, c_col in [
            ("pre6_4g_baseline", "treated_pre6_4g",   "control_pre6_4g"),
            ("log10_poblacion",  "treated_log10_pop",  "control_log10_pop"),
            ("altitud_m",        "treated_altitud_m",  "control_altitud_m"),
        ]:
            # Una observación por tratado (no duplicar por K controles)
            tv = (
                matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])[t_col]
                .first().dropna()
            )
            cv = matches[c_col].dropna()
            sp = np.sqrt((tv.var() + cv.var()) / 2) if (len(tv) > 1 and len(cv) > 1) else 1.0
            balance.append({
                "variable":     var,
                "treated_mean": tv.mean(),
                "treated_std":  tv.std(),
                "control_mean": cv.mean(),
                "control_std":  cv.std(),
                "std_diff":     (tv.mean() - cv.mean()) / sp if sp > 0 else float("nan"),
            })
        pd.DataFrame(balance).to_csv(OUT_DIR / "did_balance.csv", index=False, encoding="utf-8")
        print("\nBalance post-match:")
        for row in balance:
            print(f"  {row['variable']}: treated={row['treated_mean']:.3f}, "
                  f"control={row['control_mean']:.3f}, std_diff={row['std_diff']:.3f}")

    # ── Event study: gap(τ) para τ = -6..+5 ───────────────────────────────────
    if not matched.empty:
        print("\nComputando event study...")
        treated_ser = pd.read_csv(SERIES_PATH)
        for col in ["YEARMONTH", MEAS_COL, DL_COL]:
            if col in treated_ser.columns:
                treated_ser[col] = pd.to_numeric(treated_ser[col], errors="coerce")
        treated_ser["_key"] = treated_ser.apply(
            lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
        )

        event_rows: list[dict] = []
        for _, t in matched.iterrows():
            bp    = int(t["breakpoint_yearmonth"])
            t_key = district_key(t["department"], t["province"], t["district"])
            t_ser = treated_ser[treated_ser["_key"] == t_key]
            ctrls = matches[
                (matches["treated_dept"] == t["department"]) &
                (matches["treated_prov"] == t["province"]) &
                (matches["treated_dist"] == t["district"]) &
                (matches["treated_bp"]   == bp)
            ]

            for tau in range(-6, 6):
                cal_ym = idx_to_ym(ym_to_idx(bp) + tau)
                # Treated 4G en ese mes calendario
                t_row = t_ser[t_ser["YEARMONTH"] == cal_ym]
                if (not t_row.empty
                        and MEAS_COL in t_row.columns
                        and float(t_row[MEAS_COL].iloc[0]) > 0):
                    t_dl = float(t_row[DL_COL].iloc[0])
                else:
                    t_dl = float("nan")

                # Control 4G: media de los K controles matcheados en ese mes
                c_dls = []
                for c_key in ctrls["control_key"]:
                    if c_key in ctrl_by_key:
                        c_row = ctrl_by_key[c_key]
                        c_r = c_row[c_row["YEARMONTH"] == cal_ym]
                        if (not c_r.empty
                                and MEAS_COL in c_r.columns
                                and float(c_r[MEAS_COL].iloc[0]) > 0):
                            c_dls.append(float(c_r[DL_COL].iloc[0]))
                c_dl = float(np.mean(c_dls)) if c_dls else float("nan")

                event_rows.append({
                    "treated_key": t_key,
                    "treated_bp":  bp,
                    "tau":         tau,
                    "cal_ym":      cal_ym,
                    "treated_4g_dl":      t_dl,
                    "control_4g_dl_mean": c_dl,
                    "gap": t_dl - c_dl if not (np.isnan(t_dl) or np.isnan(c_dl)) else float("nan"),
                })

        event_df = pd.DataFrame(event_rows)
        event_agg = (
            event_df.groupby("tau")
            .agg(
                mean_treated_4g=("treated_4g_dl",      "mean"),
                mean_control_4g=("control_4g_dl_mean", "mean"),
                gap_mean=       ("gap",                 "mean"),
                gap_std=        ("gap",                 "std"),
                n=              ("gap",                 "count"),
            )
            .reset_index()
        )
        event_agg.to_csv(OUT_DIR / "event_study.csv", index=False, encoding="utf-8")

        print("Pre-trends (tau < 0, esperado: gap plano sin tendencia):")
        for _, row in event_agg[event_agg["tau"] < 0].iterrows():
            print(f"  tau={int(row['tau']):+d}: gap={row['gap_mean']:.3f} Mbps (n={int(row['n'])})")
        print("Post (tau >= 0):")
        for _, row in event_agg[event_agg["tau"] >= 0].iterrows():
            print(f"  tau={int(row['tau']):+d}: gap={row['gap_mean']:.3f} Mbps (n={int(row['n'])})")

    print(f"\nOutputs escritos en {OUT_DIR}/")
    print("  did_matches.csv, did_summary.csv, did_balance.csv, event_study.csv")


if __name__ == "__main__":
    main()
