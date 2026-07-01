import re
import numpy as np
import pandas as pd


CORE_TEXT_COLS = ["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME", "NETWORK_CARRIER"]


def _normalize_text(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )


def clean_minimal(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Normaliza textos core si existen
    for c in CORE_TEXT_COLS:
        if c in df.columns:
            df[c] = _normalize_text(df[c])

    # Carrier en mayus
    if "NETWORK_CARRIER" in df.columns:
        df["NETWORK_CARRIER"] = df["NETWORK_CARRIER"].str.upper()

    # Tipifica AÑO/MES
    if "AÑO" not in df.columns or "MES" not in df.columns:
        raise KeyError("Faltan columnas AÑO y/o MES")

    df["AÑO"] = pd.to_numeric(df["AÑO"], errors="coerce").fillna(0).astype(int)
    df["MES"] = pd.to_numeric(df["MES"], errors="coerce").fillna(0).astype(int)

    # Heurística KPI: columnas que contienen estos tokens serán numéricas y vacíos->0
    kpi_pattern = re.compile(
        r"(THROUGHPUT|LATENCY|PACKET|LOSS|TIME_PERCENTAGE|SECONDS|MEASUREMENTS|AVERAGE_)",
        re.IGNORECASE
    )

    core_keep_as_text = set(CORE_TEXT_COLS + ["AÑO", "MES", "SOURCE_FILE"])

    for col in df.columns:
        if col in core_keep_as_text:
            continue
        if kpi_pattern.search(col):
            # OSIPTEL: "" => 0
            df[col] = pd.to_numeric(df[col].replace("", np.nan), errors="coerce").fillna(0)

    return df
