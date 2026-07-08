from pathlib import Path
import pandas as pd


def sniff_delimiter(path: Path) -> str:
    """Detecta ; vs , mirando la primera linea no vacia."""
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            return ";" if line.count(";") >= line.count(",") else ","
    return ","


def read_csv_safely(path: Path) -> pd.DataFrame:
    sep = sniff_delimiter(path)
    # dtype=str para evitar problemas por columnas mixtas; luego tipificamos.
    df = pd.read_csv(path, sep=sep, encoding="utf-8", dtype=str, keep_default_na=False)
    df["ROW_PRESENT_IN_SOURCE"] = True
    return df


def read_and_concat(data_dir: Path, pattern: str = "dataset_*.csv") -> pd.DataFrame:
    files = sorted(data_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos {pattern} en {data_dir}")

    dfs = []
    for p in files:
        df = read_csv_safely(p)
        df["SOURCE_FILE"] = p.name
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)
