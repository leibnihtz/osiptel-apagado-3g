import pandas as pd


def add_yearmonth(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["YEARMONTH"] = (df["AÑO"].astype(int) * 100 + df["MES"].astype(int)).astype(int)
    return df


def add_3g_flags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    dl = "AVERAGE_THROUGHPUT_DOWNLOAD_3G"
    dlm = "THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS"

    if dl not in df.columns or dlm not in df.columns:
        missing = [c for c in [dl, dlm] if c not in df.columns]
        raise KeyError(f"Faltan columnas decisorias 3G: {missing}")

    df["IS_3G_ACTIVE_MONTH"] = (df[dl] > 0) & (df[dlm] > 0)
    df["IS_3G_ZERO_MONTH"] = (df[dl] == 0) & (df[dlm] == 0)
    return df
