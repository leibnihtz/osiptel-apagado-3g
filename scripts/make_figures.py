#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_figures.py -- IEEE LATINCOM 2026 paper figures (vector PDF).

Reads the FROZEN Phase A outputs (tag v1.0-paper-freeze) and writes three
column-width vector PDFs into paper/figs/:

    figs/map_shutdown.pdf         (Fig. 1)  confirmed districts + 4G delta
    figs/scatter_before_after.pdf (Fig. 2)  post6 vs pre6 4G download
    figs/event_study.pdf          (Fig. 3)  control-adjusted DiD by rel. month

Design goals
------------
* NUMBERS COME ONLY FROM THE FROZEN OUTPUTS. This script never hardcodes the
  paper's statistics; it plots whatever the CSV/GeoJSON contain. Run it against
  the v1.0-paper-freeze files so the figures match the text (n=67, DiD, etc.).
* Self-contained: needs only pandas + matplotlib (NO geopandas). The map reads
  GeoJSON with the standard-library json module and draws polygons directly.
* Output is IEEE-ready: Type-42 (TrueType) embedded fonts, serif, ~column width.

Usage
-----
    python Paper/make_figures.py --outdir Paper/figs

All paths have defaults matching the repo layout; override only what differs.
Column names are auto-detected from a list of candidates (see COL_* below); if
none match, the script prints the available columns and exits with a clear error.
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # headless / no display
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection
from matplotlib.colors import TwoSlopeNorm
from matplotlib.cm import ScalarMappable

# ----------------------------------------------------------------------------
# IEEE-ready matplotlib style
# ----------------------------------------------------------------------------
plt.rcParams.update({
    "pdf.fonttype": 42,          # embed TrueType (avoids Type-3; IEEE PDF check)
    "ps.fonttype": 42,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "axes.linewidth": 0.6,
    "lines.linewidth": 1.0,
    "grid.linewidth": 0.4,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

# IEEE single-column width is ~3.5 in. Keep figures at/under that.
COLW = 3.45  # inches

# Candidate column names (first match wins) -- edit if your files differ.
COL_PRE   = ["pre6_4g_download_mbps", "pre6_download_mbps", "pre_dl", "pre6_dl"]
COL_POST  = ["post6_4g_download_mbps", "post6_download_mbps", "post_dl", "post6_dl"]
COL_DELTA = ["delta_4g_download_mbps", "delta_dl", "delta_download_mbps", "delta"]
COL_REGION = ["region3", "region", "natural_region", "region_natural"]
# event_study.csv uses "tau" for the relative-month axis
COL_MONTH  = ["tau", "relative_month", "rel_month", "month_rel", "month", "k"]
# event_study.csv uses "gap_mean" for the control-adjusted effect
COL_EFFECT = ["gap_mean", "effect", "coef", "mean_diff", "did", "adj_diff",
              "mean_effect", "estimate"]
COL_CILO   = ["ci_lo", "ci95_lo", "lo", "lower", "ci_low", "conf_lo"]
COL_CIHI   = ["ci_hi", "ci95_hi", "hi", "upper", "ci_high", "conf_hi"]
# event_study_v1_2.csv uses "n_treated" for the per-tau contributing count
COL_N      = ["n_treated", "n", "n_contributing"]
# GeoJSON feature property holding the district's 4G delta:
PROP_DELTA = COL_DELTA

# Region palette (colorblind-friendly)
REGION_COLORS = {
    "costa":  "#1b6ca8", "coast":     "#1b6ca8",
    "sierra": "#c1660a", "highlands": "#c1660a",
    "selva":  "#2a8f4e", "rainforest":"#2a8f4e",
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def pick_col(df, candidates, what):
    for c in candidates:
        if c in df.columns:
            return c
    sys.exit(
        f"[make_figures] Could not find a column for '{what}'.\n"
        f"  Tried: {candidates}\n"
        f"  Available: {list(df.columns)}\n"
        f"  -> Edit the COL_* lists at the top of make_figures.py."
    )


def load_csv(path):
    if not os.path.exists(path):
        sys.exit(f"[make_figures] File not found: {path}")
    return pd.read_csv(path)


def region_key(v):
    return str(v).strip().lower()


def save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, name)
    fig.savefig(out, format="pdf")
    plt.close(fig)
    print(f"[make_figures] wrote {out}")


# ----------------------------------------------------------------------------
# Fig. 2 -- before/after scatter
# ----------------------------------------------------------------------------
def fig_scatter(summary, outdir):
    pre = pick_col(summary, COL_PRE, "pre-shutdown download")
    post = pick_col(summary, COL_POST, "post-shutdown download")
    reg = next((c for c in COL_REGION if c in summary.columns), None)

    fig, ax = plt.subplots(figsize=(COLW, COLW * 0.82))
    lim_hi = float(np.nanmax([summary[pre].max(), summary[post].max()])) * 1.05
    lim = [0, max(lim_hi, 1.0)]

    # identity line (no change)
    ax.plot(lim, lim, ls="--", color="0.4", lw=0.8, zorder=1)

    if reg is not None:
        for rv, sub in summary.groupby(summary[reg].map(region_key)):
            ax.scatter(sub[pre], sub[post], s=16, alpha=0.8, linewidths=0.3,
                       edgecolors="white",
                       color=REGION_COLORS.get(rv, "0.5"),
                       label=rv.capitalize(), zorder=2)
        ax.legend(frameon=False, loc="lower right", handletextpad=0.2,
                  borderpad=0.2, labelspacing=0.2)
    else:
        ax.scatter(summary[pre], summary[post], s=16, alpha=0.8,
                   linewidths=0.3, edgecolors="white",
                   color="#1b6ca8", zorder=2)

    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Before shutdown: avg. 4G download (Mbps)")
    ax.set_ylabel("After shutdown (Mbps)")
    ax.grid(True, color="0.9")
    ax.set_axisbelow(True)
    save(fig, outdir, "scatter_before_after.pdf")


# ----------------------------------------------------------------------------
# Fig. 3 -- event study (control-adjusted DiD by relative month)
# ----------------------------------------------------------------------------
def fig_event_study(event, outdir, out_name="event_study.pdf"):
    m = pick_col(event, COL_MONTH, "relative month")
    e = pick_col(event, COL_EFFECT, "effect / control-adjusted difference")
    lo = next((c for c in COL_CILO if c in event.columns), None)
    hi = next((c for c in COL_CIHI if c in event.columns), None)
    n_col = next((c for c in COL_N if c in event.columns), None)

    event = event.sort_values(m)
    has_n = n_col is not None
    fig, ax = plt.subplots(figsize=(COLW, COLW * (0.82 if has_n else 0.72)))

    ax.axhline(0, color="0.4", lw=0.8, ls="-")
    ax.axvline(0, color="0.4", lw=0.8, ls="--")  # breakpoint

    if lo and hi:
        ax.fill_between(event[m], event[lo], event[hi],
                        color="#1b6ca8", alpha=0.18, linewidth=0)
    ax.plot(event[m], event[e], color="#1b6ca8", marker="o",
            markersize=2.6, lw=1.0)

    ax.set_xlabel("Month relative to 3G shutdown")
    ax.set_ylabel("Control-adjusted\n4G download diff. (Mbps)")
    ax.grid(True, color="0.9")
    ax.set_axisbelow(True)

    if has_n:
        y_lo, y_hi = ax.get_ylim()
        pad = (y_hi - y_lo) * 0.16
        ax.set_ylim(y_lo - pad, y_hi)
        y_n = y_lo - pad * 0.6
        for i, (_, row) in enumerate(event.iterrows()):
            label = f"n={int(row[n_col])}" if i == 0 else f"{int(row[n_col])}"
            ax.text(row[m], y_n, label, ha="center", va="center",
                    fontsize=5.5, color="0.35")

    save(fig, outdir, out_name)


# ----------------------------------------------------------------------------
# Fig. 1 -- map (geopandas-free GeoJSON rendering)
# ----------------------------------------------------------------------------
def _iter_polys(geom):
    """Yield lists of (lon,lat) exterior rings from a GeoJSON geometry."""
    if geom is None:
        return
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Polygon":
        yield c[0]
    elif t == "MultiPolygon":
        for poly in c:
            yield poly[0]


def _ring_centroid(ring):
    """Area-weighted centroid via shoelace; fallback to vertex mean."""
    pts = np.asarray(ring, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    A = cross.sum() / 2.0
    if abs(A) < 1e-12:
        return float(x.mean()), float(y.mean())
    cx = ((x + x1) * cross).sum() / (6 * A)
    cy = ((y + y1) * cross).sum() / (6 * A)
    return cx, cy


def _load_geojson(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _feature_prop(props, candidates):
    for c in candidates:
        if c in props and props[c] is not None:
            return props[c]
    return None


def fig_map(districts_path, departments_path, outdir):
    gj = _load_geojson(districts_path)
    if gj is None:
        print(f"[make_figures] SKIP map: districts GeoJSON not found "
              f"({districts_path}). Pass --districts with the frozen file.")
        return

    deps = _load_geojson(departments_path)

    fig, ax = plt.subplots(figsize=(COLW, COLW * 1.15))

    # department borders (context)
    if deps is not None:
        patches = []
        for feat in deps.get("features", []):
            for ring in _iter_polys(feat.get("geometry")):
                patches.append(MplPolygon(np.asarray(ring, dtype=float),
                                          closed=True))
        if patches:
            ax.add_collection(PatchCollection(
                patches, facecolor="0.96", edgecolor="0.75", linewidths=0.3))

    # district bubbles: centroid, size ~ |delta|, color ~ delta
    lons, lats, vals = [], [], []
    for feat in gj.get("features", []):
        d = _feature_prop(feat.get("properties", {}), PROP_DELTA)
        if d is None:
            continue
        rings = list(_iter_polys(feat.get("geometry")))
        if not rings:
            continue
        # largest ring by vertex count as representative
        ring = max(rings, key=len)
        cx, cy = _ring_centroid(ring)
        lons.append(cx); lats.append(cy); vals.append(float(d))

    if not vals:
        sys.exit("[make_figures] map: no district features had a delta "
                 f"property {PROP_DELTA}. Check the GeoJSON.")

    vals = np.asarray(vals)
    vmax = float(np.nanmax(np.abs(vals))) or 1.0
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = plt.get_cmap("RdYlGn")
    sizes = 12 + 90 * (np.abs(vals) / vmax)

    sc = ax.scatter(lons, lats, s=sizes, c=vals, cmap=cmap, norm=norm,
                    edgecolors="0.25", linewidths=0.3, alpha=0.9, zorder=3)

    ax.set_aspect("equal", adjustable="datalim")
    ax.autoscale_view()
    ax.axis("off")

    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax,
                      orientation="horizontal", fraction=0.045, pad=0.02)
    cb.set_label("4G download change (Mbps)")
    cb.ax.tick_params(labelsize=6)
    save(fig, outdir, "map_shutdown.pdf")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate IEEE paper figures.")
    ap.add_argument("--summary",
                    default="outputs/observable/data/observable_4g_upgrade_summary_with_ubigeo.csv")
    ap.add_argument("--event",
                    default="outputs/tables/event_study.csv")
    ap.add_argument("--districts",
                    default="outputs/observable/data/observable_4g_upgrade_districts.geojson")
    ap.add_argument("--departments",
                    default="outputs/observable/data/observable_departments_inei_2023_simplified.geojson")
    ap.add_argument("--outdir", default="Paper/figs")
    ap.add_argument("--out-name", default="event_study.pdf",
                    help="output filename for the event-study figure")
    ap.add_argument("--only", choices=["map", "scatter", "event"], default=None,
                    help="generate only one figure")
    args = ap.parse_args()

    if args.only in (None, "scatter"):
        fig_scatter(load_csv(args.summary), args.outdir)
    if args.only in (None, "event"):
        fig_event_study(load_csv(args.event), args.outdir, out_name=args.out_name)
    if args.only in (None, "map"):
        fig_map(args.districts, args.departments, args.outdir)

    print("[make_figures] done.")


if __name__ == "__main__":
    main()
