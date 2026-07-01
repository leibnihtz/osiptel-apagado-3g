#!/usr/bin/env python3
"""
Descarga el dataset del año en curso desde la API de OSIPTEL,
corre el pipeline Python y escribe los outputs finales.

Uso local:
    python scripts/download.py

GitHub Actions lo ejecuta automáticamente cada mes.
"""
import io
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from portalosiptel3g.io import read_and_concat
from portalosiptel3g.cleaning import clean_minimal
from portalosiptel3g.features import add_yearmonth, add_3g_flags
from portalosiptel3g.detection import detect_shutdown_confirmed

OSIPTEL_URL = "https://checatuinternetmovil.osiptel.gob.pe/beta/api/Indicador/obtener-dataset"
CARRIER = "MOVISTAR"


def download_year_csv(year: int) -> Path:
    dest = ROOT / "data" / "raw" / f"dataset_{year}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Descargando dataset {year} desde OSIPTEL...")
    r = requests.get(OSIPTEL_URL, params={"anio": year}, timeout=120)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        # El ZIP contiene dataset.csv y diccionario-datos.xlsx — solo nos interesa el CSV
        z.extract("dataset.csv", path=dest.parent)
        (dest.parent / "dataset.csv").rename(dest)

    print(f"  Guardado: {dest.name}  ({dest.stat().st_size / 1_048_576:.1f} MB)")
    return dest


def run_pipeline() -> None:
    data_dir = ROOT / "data" / "raw"
    print(f"Leyendo CSVs de {data_dir} ...")
    df = read_and_concat(data_dir, pattern="dataset_*.csv")
    print(f"  Filas totales: {len(df):,}")

    df = clean_minimal(df)
    df = add_yearmonth(df)
    df = add_3g_flags(df)

    print(f"Detectando shutdown (carrier={CARRIER}) ...")
    core = detect_shutdown_confirmed(df, carrier=CARRIER)
    print(f"  Distritos SHUTDOWN_CONFIRMED: {len(core)}")

    keys = ["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME", "NETWORK_CARRIER"]
    final = df.merge(core[keys], on=keys, how="inner")

    out_final = ROOT / "osiptel_series_final.csv"
    final.to_csv(out_final, index=False, encoding="utf-8")
    print(f"  osiptel_series_final.csv: {len(final):,} filas → {out_final}")

    tables_dir = ROOT / "outputs" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    final.to_csv(tables_dir / "dataset_2023_2025_shutdown_districts.csv", index=False, encoding="utf-8")
    print("  dataset_2023_2025_shutdown_districts.csv actualizado")
    core.to_csv(tables_dir / "shutdown_confirmed.csv", index=False, encoding="utf-8")
    print("  shutdown_confirmed.csv actualizado")

    print("Generando outputs Observable-ready ...")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_observable_outputs.py"),
            "--series",
            str(tables_dir / "dataset_2023_2025_shutdown_districts.csv"),
            "--shutdown",
            str(tables_dir / "shutdown_confirmed.csv"),
        ],
        check=True,
    )


def main() -> None:
    year = datetime.now().year
    download_year_csv(year)
    run_pipeline()
    print("Pipeline completado")


if __name__ == "__main__":
    main()
