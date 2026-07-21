#!/usr/bin/env python3
"""
v1.1 — Extensión multi-outcome del DiD (SPEC: Paper/spec_v1_1_multioutcome.md).

NO rediseña nada: reutiliza TAL CUAL los pares tratado-control de
outputs/tables/did_matches.csv (matching Mahalanobis K=5 congelado en v1.0).
Solo cambia las columnas de outcome que se evalúan sobre esos mismos pares,
misma ventana (6 meses pre/post) y misma exclusión
(THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS == 0).

Input:
  outputs/tables/did_matches.csv
  outputs/tables/shutdown_confirmed.csv   (solo para PASO 0 / referencia)
  data/raw/dataset_*.csv

Output:
  outputs/tables/observable_stats_v1_1.json
  outputs/tables/did_summary_v1_1.csv     (did por distrito x outcome, para auditoría)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as spstats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portalosiptel3g.cleaning import clean_minimal
from portalosiptel3g.features import add_yearmonth, add_3g_flags

RAW_DIR     = ROOT / "data" / "raw"
MATCHES_PATH = ROOT / "outputs" / "tables" / "did_matches.csv"
OUT_JSON    = ROOT / "outputs" / "tables" / "observable_stats_v1_1.json"
OUT_CSV     = ROOT / "outputs" / "tables" / "did_summary_v1_1.csv"

MEAS_COL  = "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"
BOOT_SEED = 42
BOOT_N    = 10_000

# tag -> (columna OSIPTEL, unidad, direccion de mejora, rol)
OUTCOMES = {
    "download":    ("AVERAGE_THROUGHPUT_DOWNLOAD_4G", "Mbps", "up",   "principal (ya congelado)"),
    "time4g":      ("TIME_PERCENTAGE_4G",              "p.p.", "up",   "2º outcome causal (mecanismo)"),
    "latency":     ("AVERAGE_LATENCY_4G",               "ms",   "down", "robustez tecnica"),
    "upload":      ("AVERAGE_THROUGHPUT_UPLOAD_4G",     "Mbps", "up",   "secundario"),
    "packet_loss": ("PACKET_LOSS_4G",                   "p.p.", "down", "secundario"),
}

SANITY_DOWNLOAD_DID_MEDIAN = 0.6488
SANITY_TOL = 1e-4
SANITY_N_MATCHED = 67
SANITY_N_POSITIVE = 52


def ym_to_idx(ym: int) -> int:
    return (ym // 100) * 12 + (ym % 100) - 1


def idx_to_ym(idx: int) -> int:
    year, month = divmod(idx, 12)
    return year * 100 + month + 1


def window_months(bp: int) -> tuple[list[int], list[int]]:
    bp_idx = ym_to_idx(bp)
    pre  = [idx_to_ym(bp_idx - 6 + i) for i in range(6)]
    post = [idx_to_ym(bp_idx + i)      for i in range(6)]
    return pre, post


def district_key(dept: str, prov: str, dist: str) -> str:
    return (
        str(dept).upper().strip() + "|"
        + str(prov).upper().strip() + "|"
        + str(dist).upper().strip()
    )


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
    numeric_cols = {MEAS_COL} | {c for c, *_ in OUTCOMES.values()}
    numeric_cols |= {
        "THROUGHPUT_DOWNLOAD_5G_NSA_MEASUREMENTS",
        "THROUGHPUT_UPLOAD_5G_NSA_MEASUREMENTS",
        "LATENCY_5G_NSA_MEASUREMENTS",
        "TIME_PERCENTAGE_5G_NSA_MEASUREMENTS",
        "TIME_PERCENTAGE_5G_NSA",
    }
    for col in numeric_cols:
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
    return raw


def mean_valid(g: pd.DataFrame, outcome_col: str) -> float:
    """Media del outcome_col sobre meses con MEAS_COL > 0 (misma regla que download)."""
    if MEAS_COL not in g.columns or outcome_col not in g.columns:
        return float("nan")
    rows = g[g[MEAS_COL] > 0]
    if rows.empty:
        return float("nan")
    return float(rows[outcome_col].mean())


def bootstrap_median_ci(data: np.ndarray, n_boot: int = BOOT_N, ci: float = 0.95, seed: int = BOOT_SEED):
    rng = np.random.default_rng(seed)
    medians = np.array([
        np.median(rng.choice(data, size=len(data), replace=True))
        for _ in range(n_boot)
    ])
    alpha = (1 - ci) / 2
    return float(np.percentile(medians, 100 * alpha)), float(np.percentile(medians, 100 * (1 - alpha)))


def _round_p(p: float) -> float:
    return float(f"{p:.2e}") if p < 1e-4 else round(p, 6)


def outcome_stats(rows: list[dict], tag: str, col: str, unit: str, improve: str, role: str) -> dict:
    did_vec = np.array([r["did"] for r in rows])
    delta_crude = np.array([r["delta_treated"] for r in rows])
    n = len(rows)

    raw_median = float(np.median(delta_crude))
    did_median = float(np.median(did_vec))
    did_mean   = float(did_vec.mean())
    did_std    = float(did_vec.std())
    ci_lo, ci_hi = bootstrap_median_ci(did_vec, seed=BOOT_SEED)

    if improve == "up":
        n_pos = int((did_vec > 0).sum())
        n_neg = int((did_vec < 0).sum())
    else:
        n_pos = int((did_vec < 0).sum())
        n_neg = int((did_vec > 0).sum())

    w_p_two = float(spstats.wilcoxon(did_vec, alternative="two-sided").pvalue)
    entry = {
        "column": col,
        "unit": unit,
        "improve": improve,
        "role": role,
        "raw_median": round(raw_median, 4),
        "did_median": round(did_median, 4),
        "did_mean": round(did_mean, 4),
        "did_std": round(did_std, 4),
        "ci95_lo": round(ci_lo, 4),
        "ci95_hi": round(ci_hi, 4),
        "wilcoxon_p_twosided": _round_p(w_p_two),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n": n,
    }
    if tag == "download":
        w_p_one = float(spstats.wilcoxon(did_vec, alternative="greater").pvalue)
        entry["wilcoxon_p_onesided"] = _round_p(w_p_one)
    else:
        entry["wilcoxon_p_onesided"] = None
    return entry


def main() -> None:
    print("Cargando dataset completo MOVISTAR (misma carga que v1.0)...")
    full = load_full_movistar()
    global_months = set(int(m) for m in full["YEARMONTH"].dropna().unique())
    full["_key"] = full.apply(
        lambda r: district_key(r["ADM_LEVEL_1_NAME"], r["ADM_LEVEL_2_NAME"], r["ADM_LEVEL_3_NAME"]), axis=1
    )
    by_key: dict[str, pd.DataFrame] = {
        key: g.sort_values("YEARMONTH").reset_index(drop=True)
        for key, g in full.groupby("_key")
    }
    print(f"  {len(full):,} filas MOVISTAR — {len(by_key):,} distritos (tratados + control)")

    print("\nCargando pares tratado-control congelados (did_matches.csv, TAL CUAL v1.0)...")
    matches = pd.read_csv(MATCHES_PATH, encoding="utf-8")
    treated_groups = matches.groupby(["treated_dept", "treated_prov", "treated_dist", "treated_bp"])
    n_treated = treated_groups.ngroups
    print(f"  {len(matches)} filas de match — {n_treated} distritos tratados")

    # Acumuladores: outcome_tag -> lista de dict por distrito tratado
    per_outcome_rows: dict[str, list[dict]] = {tag: [] for tag in OUTCOMES}
    meas_change_rows: list[float] = []
    has5g_rows: list[dict] = []

    for (dept, prov, dist, bp), grp in treated_groups:
        bp = int(bp)
        pre_m, post_m = window_months(bp)
        pre_m_avail  = [m for m in pre_m  if m in global_months]
        post_m_avail = [m for m in post_m if m in global_months]

        t_key = district_key(dept, prov, dist)
        g_t = by_key.get(t_key)
        if g_t is None:
            print(f"  AVISO: tratado sin datos crudos: {t_key} — se omite")
            continue
        g_t_pre  = g_t[g_t["YEARMONTH"].isin(pre_m_avail)]
        g_t_post = g_t[g_t["YEARMONTH"].isin(post_m_avail)]

        control_keys = grp["control_key"].tolist()
        ctrl_series = []
        for c_key in control_keys:
            g_c = by_key.get(c_key)
            if g_c is None:
                continue
            g_c_pre  = g_c[g_c["YEARMONTH"].isin(pre_m_avail)]
            g_c_post = g_c[g_c["YEARMONTH"].isin(post_m_avail)]
            ctrl_series.append((g_c_pre, g_c_post))

        # ── outcomes de throughput/latency/etc. ──────────────────────────────
        for tag, (col, unit, improve, role) in OUTCOMES.items():
            pre_t  = mean_valid(g_t_pre,  col)
            post_t = mean_valid(g_t_post, col)
            if np.isnan(pre_t) or np.isnan(post_t):
                continue
            delta_t = post_t - pre_t

            ctrl_deltas = []
            for g_c_pre, g_c_post in ctrl_series:
                pre_c  = mean_valid(g_c_pre,  col)
                post_c = mean_valid(g_c_post, col)
                if not (np.isnan(pre_c) or np.isnan(post_c)):
                    ctrl_deltas.append(post_c - pre_c)
            if not ctrl_deltas:
                continue
            delta_c_mean = float(np.mean(ctrl_deltas))
            did = delta_t - delta_c_mean

            per_outcome_rows[tag].append({
                "department": dept, "province": prov, "district": dist,
                "breakpoint_yearmonth": bp,
                "delta_treated": delta_t, "delta_control_mean": delta_c_mean, "did": did,
                "n_controls": len(ctrl_deltas),
            })

        # ── PASO 3: volumen de mediciones ────────────────────────────────────
        pre_meas  = g_t_pre[MEAS_COL].mean()  if MEAS_COL in g_t_pre.columns  and not g_t_pre.empty  else float("nan")
        post_meas = g_t_post[MEAS_COL].mean() if MEAS_COL in g_t_post.columns and not g_t_post.empty else float("nan")
        if not (np.isnan(pre_meas) or np.isnan(post_meas)):
            meas_change_rows.append(post_meas - pre_meas)

        # ── PASO 4: presencia de 5G en ventana post ──────────────────────────
        col_5g_meas = "THROUGHPUT_DOWNLOAD_5G_NSA_MEASUREMENTS"
        has_5g = False
        if col_5g_meas in g_t_post.columns and not g_t_post.empty:
            has_5g = bool((g_t_post[col_5g_meas].fillna(0) > 0).any())
        has5g_rows.append({
            "department": dept, "province": prov, "district": dist, "breakpoint_yearmonth": bp,
            "has_5g_post": has_5g,
        })

    # ── PASO 0: sanity check sobre download ──────────────────────────────────
    dl_rows = per_outcome_rows["download"]
    dl_did = np.array([r["did"] for r in dl_rows])
    n_matched_dl = len(dl_did)
    n_pos_dl = int((dl_did > 0).sum())
    dl_median = float(np.median(dl_did))

    print("\n=== PASO 0 — Sanity check (download) ===")
    print(f"  did.median(download) = {dl_median:.4f}  (esperado {SANITY_DOWNLOAD_DID_MEDIAN}, tol {SANITY_TOL})")
    print(f"  n_matched = {n_matched_dl}  (esperado {SANITY_N_MATCHED})")
    print(f"  n_positive = {n_pos_dl}  (esperado {SANITY_N_POSITIVE})")

    ok = (
        abs(dl_median - SANITY_DOWNLOAD_DID_MEDIAN) < SANITY_TOL
        and n_matched_dl == SANITY_N_MATCHED
        and n_pos_dl == SANITY_N_POSITIVE
    )
    if not ok:
        print("\n*** SANITY CHECK FALLIDO — el diseño derivó respecto a v1.0-paper-freeze. DETENIENDO. ***")
        sys.exit(1)
    print("  Sanity check OK — el diseño no derivó, se continúa.\n")

    # ── PASO 1/2: estadísticos por outcome (muestra completa, n=67) ──────────
    outcomes_out = {}
    all_summary_rows = []
    has5g_by_key = {
        (r["department"], r["province"], r["district"], r["breakpoint_yearmonth"]): r["has_5g_post"]
        for r in has5g_rows
    }
    excluded_5g = sorted({
        (d, p, i) for (d, p, i, _bp), has5g in has5g_by_key.items() if has5g
    })

    for tag, (col, unit, improve, role) in OUTCOMES.items():
        rows = per_outcome_rows[tag]
        entry = outcome_stats(rows, tag, col, unit, improve, role)
        outcomes_out[tag] = entry
        print(f"[{tag:11s}] raw_median={entry['raw_median']:+.4f} did_median={entry['did_median']:+.4f} "
              f"IC95=[{entry['ci95_lo']:+.4f},{entry['ci95_hi']:+.4f}] p2s={entry['wilcoxon_p_twosided']:.3g} "
              f"n_pos={entry['n_positive']} n_neg={entry['n_negative']} n={entry['n']}")

        for r in rows:
            key = (r["department"], r["province"], r["district"], r["breakpoint_yearmonth"])
            all_summary_rows.append({
                "outcome": tag, **r,
                "has_5g_post": has5g_by_key.get(key, False),
            })

    # ── Robustez: variante excl_5g_contaminated (n=60, sin los 7 distritos ──
    # con mediciones 5G NSA presentes en su ventana post — ver PASO 4).
    outcomes_excl5g = {}
    for tag, (col, unit, improve, role) in OUTCOMES.items():
        rows = [
            r for r in per_outcome_rows[tag]
            if not has5g_by_key.get(
                (r["department"], r["province"], r["district"], r["breakpoint_yearmonth"]), False
            )
        ]
        outcomes_excl5g[tag] = outcome_stats(rows, tag, col, unit, improve, role)

    print(f"\n[Robustez excl_5g] n_excluidos={len(excluded_5g)} -> n={outcomes_excl5g['download']['n']}")
    for tag, entry in outcomes_excl5g.items():
        print(f"  [{tag:11s}] did_median={entry['did_median']:+.4f} IC95=[{entry['ci95_lo']:+.4f},{entry['ci95_hi']:+.4f}] n={entry['n']}")

    # ── PASO 3: robustez de volumen muestral ─────────────────────────────────
    meas_arr = np.array(meas_change_rows)
    meas_change_median = float(np.median(meas_arr)) if len(meas_arr) else None
    print(f"\n[PASO 3] meas_change_median (post6-pre6 conteo mediciones 4G) = {meas_change_median}")

    # ── PASO 4: chequeo de 5G ─────────────────────────────────────────────────
    col_pattern_5g = [c for c in full.columns if "5G" in c.upper()]
    has_5g_columns = len(col_pattern_5g) > 0
    n_treated_with_5g = sum(1 for r in has5g_rows if r["has_5g_post"])
    print(f"[PASO 4] has_5g_columns={has_5g_columns} ({len(col_pattern_5g)} columnas 5G_NSA encontradas)")
    print(f"[PASO 4] distritos tratados con 5G_NSA presente en ventana post: {n_treated_with_5g}/{len(has5g_rows)}")

    # ── Salida ────────────────────────────────────────────────────────────────
    stats = {
        "tag": "v1.1-outcomes (design unchanged vs v1.0-paper-freeze)",
        "sanity_download_did_median": round(dl_median, 4),
        "outcomes": outcomes_out,
        "robustness": {
            "meas_change_median": round(meas_change_median, 2) if meas_change_median is not None else None,
            "meas_change_note": "cambio del conteo de mediciones 4G (post6-pre6) en el breakpoint, mediana sobre los 67 tratados",
            "excl_5g_contaminated": {
                "note": "n=60, excluye los distritos tratados con mediciones 5G_NSA>0 en su ventana post (ver PASO 4)",
                "n_excluded": len(excluded_5g),
                "excluded_districts": [
                    {"department": d, "province": p, "district": i} for d, p, i in excluded_5g
                ],
                "outcomes": outcomes_excl5g,
            },
        },
        "has_5g_columns": has_5g_columns,
        "n_treated_with_5g_post": n_treated_with_5g,
        "n_treated_total": len(has5g_rows),
        "bootstrap": {"seed": BOOT_SEED, "n_iterations": BOOT_N},
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame(all_summary_rows).to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"\nEscrito: {OUT_JSON}")
    print(f"Escrito: {OUT_CSV}")


if __name__ == "__main__":
    main()
