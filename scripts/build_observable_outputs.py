#!/usr/bin/env python3
"""
Build Observable-ready outputs from the OSIPTEL shutdown pipeline.

Inputs:
  - monthly district/carrier series filtered to confirmed 3G shutdown districts
  - shutdown_confirmed.csv with each district breakpoint
  - simplified Peru district GeoJSON with UBIGEO and district names

Outputs:
  - CSV summary with pre/post 4G upgrade metrics
  - CSV monthly time series with relative_month
  - GeoJSON for all districts, with metrics injected where available
  - GeoJSON for only the confirmed shutdown districts

The main upgrade metric is:
  average 4G download in the first 6 post-shutdown months
  minus average 4G download in the last 6 pre-shutdown months.
"""
from __future__ import annotations

import argparse
import json
import math
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
KEYS = ["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME", "NETWORK_CARRIER"]


def normalize_name(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().upper()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    for old, new in [(".", ""), (",", ""), ("'", ""), ("-", " ")]:
        text = text.replace(old, new)
    return " ".join(text.split())


def geo_key(department: Any, province: Any, district: Any) -> tuple[str, str, str]:
    return (normalize_name(department), normalize_name(province), normalize_name(district))


def yearmonth_index(yearmonth: pd.Series) -> pd.Series:
    yearmonth = yearmonth.astype(int)
    return (yearmonth // 100) * 12 + (yearmonth % 100)


def mean_or_na(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return math.nan
    return float(frame[column].mean(skipna=True))


def ratio_change(after: float, before: float) -> float:
    if pd.isna(after) or pd.isna(before) or before == 0:
        return math.nan
    return float(after / before - 1)


def improvement_ratio(before: float, after: float) -> float:
    if pd.isna(after) or pd.isna(before) or after == 0:
        return math.nan
    return float(before / after - 1)


def numeric_or_none(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (int, str, bool)):
        return value
    return value


def build_summary(series: pd.DataFrame, shutdown: pd.DataFrame) -> pd.DataFrame:
    data = series.merge(shutdown, on=KEYS, how="inner")

    numeric_cols = [
        "YEARMONTH",
        "BREAKPOINT_YEARMONTH",
        "LAST_YEARMONTH_AVAILABLE",
        "AVERAGE_THROUGHPUT_DOWNLOAD_4G",
        "AVERAGE_THROUGHPUT_UPLOAD_4G",
        "AVERAGE_LATENCY_4G",
        "TIME_PERCENTAGE_4G",
        "PACKET_LOSS_4G",
        "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS",
        "LATENCY_4G_MEASUREMENTS",
        "TIME_PERCENTAGE_TOTAL_SECONDS",
    ]
    for col in numeric_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    rows: list[dict[str, Any]] = []
    for key, group in data.groupby(KEYS, dropna=False):
        group = group.sort_values("YEARMONTH")
        breakpoint = int(group["BREAKPOINT_YEARMONTH"].iloc[0])
        pre_all = group[group["YEARMONTH"] < breakpoint]
        post_all = group[group["YEARMONTH"] >= breakpoint]
        pre6 = pre_all.tail(6)
        post6 = post_all.head(6)

        pre_dl = mean_or_na(pre6, "AVERAGE_THROUGHPUT_DOWNLOAD_4G")
        post_dl = mean_or_na(post6, "AVERAGE_THROUGHPUT_DOWNLOAD_4G")
        pre_ul = mean_or_na(pre6, "AVERAGE_THROUGHPUT_UPLOAD_4G")
        post_ul = mean_or_na(post6, "AVERAGE_THROUGHPUT_UPLOAD_4G")
        pre_latency = mean_or_na(pre6, "AVERAGE_LATENCY_4G")
        post_latency = mean_or_na(post6, "AVERAGE_LATENCY_4G")
        pre_time = mean_or_na(pre6, "TIME_PERCENTAGE_4G")
        post_time = mean_or_na(post6, "TIME_PERCENTAGE_4G")
        pre_loss = mean_or_na(pre6, "PACKET_LOSS_4G")
        post_loss = mean_or_na(post6, "PACKET_LOSS_4G")

        dl_pct = ratio_change(post_dl, pre_dl)
        ul_pct = ratio_change(post_ul, pre_ul)
        latency_pct = improvement_ratio(pre_latency, post_latency)
        time_pp = post_time - pre_time if pd.notna(post_time) and pd.notna(pre_time) else math.nan
        loss_pct = improvement_ratio(pre_loss, post_loss)

        weighted_parts = []
        weights = []
        for value, weight in [
            (dl_pct, 0.40),
            (ul_pct, 0.15),
            (latency_pct, 0.25),
            ((time_pp / 100) if pd.notna(time_pp) else math.nan, 0.15),
            (loss_pct, 0.05),
        ]:
            if pd.notna(value):
                weighted_parts.append(float(value) * weight)
                weights.append(weight)
        score = sum(weighted_parts) / sum(weights) if weights else math.nan

        department, province, district, carrier = key
        rows.append(
            {
                "department": department,
                "province": province,
                "district": district,
                "carrier": carrier,
                "breakpoint_yearmonth": breakpoint,
                "months_pre": int(len(pre_all)),
                "months_post": int(len(post_all)),
                "pre6_4g_download_mbps": pre_dl,
                "post6_4g_download_mbps": post_dl,
                "delta_4g_download_mbps": post_dl - pre_dl,
                "pct_4g_download_upgrade": dl_pct,
                "pre6_4g_upload_mbps": pre_ul,
                "post6_4g_upload_mbps": post_ul,
                "delta_4g_upload_mbps": post_ul - pre_ul,
                "pct_4g_upload_upgrade": ul_pct,
                "pre6_4g_latency_ms": pre_latency,
                "post6_4g_latency_ms": post_latency,
                "delta_4g_latency_ms": post_latency - pre_latency,
                "pct_4g_latency_improvement": latency_pct,
                "pre6_4g_time_pct": pre_time,
                "post6_4g_time_pct": post_time,
                "delta_4g_time_pp": time_pp,
                "pre6_4g_packet_loss_pct": pre_loss,
                "post6_4g_packet_loss_pct": post_loss,
                "delta_4g_packet_loss_pp": post_loss - pre_loss,
                "pct_4g_packet_loss_improvement": loss_pct,
                "composite_upgrade_score": score,
                "pre6_4g_download_measurements": mean_or_na(pre6, "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"),
                "post6_4g_download_measurements": mean_or_na(post6, "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS"),
                "last_yearmonth_available": int(group["LAST_YEARMONTH_AVAILABLE"].iloc[0])
                if "LAST_YEARMONTH_AVAILABLE" in group.columns and pd.notna(group["LAST_YEARMONTH_AVAILABLE"].iloc[0])
                else int(group["YEARMONTH"].max()),
            }
        )

    return pd.DataFrame(rows).sort_values("composite_upgrade_score", ascending=False)


def build_timeseries(series: pd.DataFrame, shutdown: pd.DataFrame) -> pd.DataFrame:
    data = series.merge(shutdown, on=KEYS, how="inner")
    data["YEARMONTH"] = pd.to_numeric(data["YEARMONTH"], errors="coerce").astype(int)
    data["BREAKPOINT_YEARMONTH"] = pd.to_numeric(data["BREAKPOINT_YEARMONTH"], errors="coerce").astype(int)
    data["relative_month"] = yearmonth_index(data["YEARMONTH"]) - yearmonth_index(data["BREAKPOINT_YEARMONTH"])
    data["period"] = data["relative_month"].map(lambda x: "pre_shutdown" if x < 0 else "post_shutdown")
    data["district_label"] = (
        data["ADM_LEVEL_3_NAME"] + ", " + data["ADM_LEVEL_2_NAME"] + ", " + data["ADM_LEVEL_1_NAME"]
    )

    keep = [
        "ADM_LEVEL_1_NAME",
        "ADM_LEVEL_2_NAME",
        "ADM_LEVEL_3_NAME",
        "district_label",
        "NETWORK_CARRIER",
        "YEARMONTH",
        "BREAKPOINT_YEARMONTH",
        "relative_month",
        "period",
        "AVERAGE_THROUGHPUT_DOWNLOAD_3G",
        "THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS",
        "AVERAGE_THROUGHPUT_DOWNLOAD_4G",
        "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS",
        "AVERAGE_THROUGHPUT_UPLOAD_4G",
        "AVERAGE_LATENCY_4G",
        "TIME_PERCENTAGE_3G",
        "TIME_PERCENTAGE_4G",
        "PACKET_LOSS_4G",
        "IS_3G_ACTIVE_MONTH",
        "IS_3G_ZERO_MONTH",
    ]
    existing = [col for col in keep if col in data.columns]
    return data[existing].sort_values(["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME", "YEARMONTH"])


def inject_geo_metrics(summary: pd.DataFrame, geo_path: Path) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    geo = json.loads(geo_path.read_text(encoding="utf-8"))

    summary_by_key = {
        geo_key(row.department, row.province, row.district): row._asdict()
        for row in summary.itertuples(index=False)
    }

    enriched_rows: list[dict[str, Any]] = []
    shutdown_features: list[dict[str, Any]] = []

    for feature in geo["features"]:
        props = feature.get("properties", {})
        ubigeo = str(props.get("ubigeo", "")).zfill(6)
        key = geo_key(props.get("department"), props.get("province"), props.get("district"))
        metrics = summary_by_key.get(key)

        base_props = {
            "ubigeo": ubigeo,
            "department": props.get("department", ""),
            "province": props.get("province", ""),
            "district": props.get("district", ""),
            "has_shutdown_3g": metrics is not None,
        }

        if metrics:
            enriched = dict(metrics)
            enriched["ubigeo"] = ubigeo
            enriched["shape_department"] = props.get("department", "")
            enriched["shape_province"] = props.get("province", "")
            enriched["shape_district"] = props.get("district", "")
            enriched_rows.append(enriched)

            metric_props = {k: numeric_or_none(v) for k, v in metrics.items()}
            feature["properties"] = {**base_props, **metric_props}
            shutdown_features.append(
                {
                    "type": "Feature",
                    "properties": {**base_props, **metric_props},
                    "geometry": feature["geometry"],
                }
            )
        else:
            feature["properties"] = {
                **base_props,
                "carrier": None,
                "breakpoint_yearmonth": None,
                "months_pre": None,
                "months_post": None,
                "pre6_4g_download_mbps": None,
                "post6_4g_download_mbps": None,
                "delta_4g_download_mbps": None,
                "pct_4g_download_upgrade": None,
                "delta_4g_latency_ms": None,
                "delta_4g_time_pp": None,
                "composite_upgrade_score": None,
            }

    all_geo = geo
    shutdown_geo = {"type": "FeatureCollection", "features": shutdown_features}
    return all_geo, shutdown_geo, pd.DataFrame(enriched_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Observable-ready OSIPTEL outputs.")
    parser.add_argument(
        "--series",
        type=Path,
        default=None,
        help="Filtered monthly series CSV. Defaults to outputs/tables/dataset_2023_2025_shutdown_districts.csv, then osiptel_series_final.csv.",
    )
    parser.add_argument(
        "--shutdown",
        type=Path,
        default=ROOT / "outputs" / "tables" / "shutdown_confirmed.csv",
        help="shutdown_confirmed.csv path.",
    )
    parser.add_argument(
        "--geo",
        type=Path,
        default=ROOT / "data" / "geo" / "peru_districts_simplified.geojson",
        help="Simplified Peru district GeoJSON path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs" / "observable" / "data",
        help="Directory for Observable-ready files.",
    )
    return parser.parse_args()


def resolve_series_path(arg_path: Path | None) -> Path:
    if arg_path:
        return arg_path

    candidates = [
        ROOT / "outputs" / "tables" / "dataset_2023_2025_shutdown_districts.csv",
        ROOT / "osiptel_series_final.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("No series CSV found. Expected outputs/tables/dataset_2023_2025_shutdown_districts.csv or osiptel_series_final.csv")


def main() -> None:
    args = parse_args()
    series_path = resolve_series_path(args.series)

    print(f"Reading series: {series_path}")
    series = pd.read_csv(series_path)
    print(f"Reading shutdown table: {args.shutdown}")
    shutdown = pd.read_csv(args.shutdown)
    print(f"Reading district geometry: {args.geo}")

    summary = build_summary(series, shutdown)
    timeseries = build_timeseries(series, shutdown)
    all_geo, shutdown_geo, summary_with_ubigeo = inject_geo_metrics(summary, args.geo)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = args.output_dir / "observable_4g_upgrade_summary.csv"
    summary_ubigeo_path = args.output_dir / "observable_4g_upgrade_summary_with_ubigeo.csv"
    timeseries_path = args.output_dir / "observable_shutdown_timeseries.csv"
    all_geo_path = args.output_dir / "observable_all_districts_with_upgrade_simplified.geojson"
    shutdown_geo_path = args.output_dir / "observable_4g_upgrade_districts.geojson"

    summary.to_csv(summary_path, index=False, encoding="utf-8")
    summary_with_ubigeo.to_csv(summary_ubigeo_path, index=False, encoding="utf-8")
    timeseries.to_csv(timeseries_path, index=False, encoding="utf-8")
    all_geo_path.write_text(json.dumps(all_geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutdown_geo_path.write_text(json.dumps(shutdown_geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"Observable summary rows: {len(summary)}")
    print(f"Observable time series rows: {len(timeseries)}")
    print(f"Matched GeoJSON districts: {len(shutdown_geo['features'])}/{len(summary)}")
    print(f"Wrote: {args.output_dir}")


if __name__ == "__main__":
    main()
