#!/usr/bin/env python3
"""
Download the current OSIPTEL dataset, run the shutdown pipeline, and build
Observable-ready outputs.

GitHub Actions runs this script monthly.
"""
import io
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from portalosiptel3g.cleaning import clean_minimal
from portalosiptel3g.detection import detect_shutdown_confirmed
from portalosiptel3g.features import add_3g_flags, add_yearmonth
from portalosiptel3g.io import read_and_concat


# OSIPTEL currently uses a certificate chain that may fail in Linux runners.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://checatuinternetmovil.osiptel.gob.pe"
OSIPTEL_URL = f"{BASE_URL}/beta/api/Indicador/obtener-dataset"
OSIPTEL_INFO_URL = f"{BASE_URL}/beta/api/info"
CARRIER = "MOVISTAR"

# These values are used by the public Angular frontend to decrypt the token
# returned by /beta/api/info before calling API endpoints.
OSIPTEL_AES_KEY = b"36283373235651607628037193265164"
OSIPTEL_AES_IV = b"6268530695511607"

JSON_TO_LEGACY_COLUMNS = {
    "anio": "AÑO",
    "mes": "MES",
    "admLevel1Name": "ADM_LEVEL_1_NAME",
    "admLevel2Name": "ADM_LEVEL_2_NAME",
    "admLevel3Name": "ADM_LEVEL_3_NAME",
    "networkCarrier": "NETWORK_CARRIER",
    "averageThroughputDownload3G": "AVERAGE_THROUGHPUT_DOWNLOAD_3G",
    "throughputDownload3GMeasurements": "THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS",
    "averageThroughputUpload3G": "AVERAGE_THROUGHPUT_UPLOAD_3G",
    "throughputUpload3GMeasurements": "THROUGHPUT_UPLOAD_3G_MEASUREMENTS",
    "averageThroughputDownload4G": "AVERAGE_THROUGHPUT_DOWNLOAD_4G",
    "throughputDownload4GMeasurements": "THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS",
    "averageThroughputUpload4G": "AVERAGE_THROUGHPUT_UPLOAD_4G",
    "throughputUpload4GMeasurements": "THROUGHPUT_UPLOAD_4G_MEASUREMENTS",
    "averageThroughputDownload5GNsa": "AVERAGE_THROUGHPUT_DOWNLOAD_5G_NSA",
    "throughputDownload5GNsaMeasurements": "THROUGHPUT_DOWNLOAD_5G_NSA_MEASUREMENTS",
    "averageThroughputUpload5GNsa": "AVERAGE_THROUGHPUT_UPLOAD_5G_NSA",
    "throughputUpload5GNsaMeasurements": "THROUGHPUT_UPLOAD_5G_NSA_MEASUREMENTS",
    "averageLatency3G": "AVERAGE_LATENCY_3G",
    "latency3GMeasurements": "LATENCY_3G_MEASUREMENTS",
    "averageLatency4G": "AVERAGE_LATENCY_4G",
    "latency4GMeasurements": "LATENCY_4G_MEASUREMENTS",
    "averageLatency5GNsa": "AVERAGE_LATENCY_5G_NSA",
    "latency5GNsaMeasurements": "LATENCY_5G_NSA_MEASUREMENTS",
    "tCob3G": "TIME_PERCENTAGE_3G",
    "timePercentage3GSeconds": "TIME_PERCENTAGE_3G_SECONDS",
    "time_percentage_3G_measurements": "TIME_PERCENTAGE_3G_MEASUREMENTS",
    "tCob4G": "TIME_PERCENTAGE_4G",
    "timePercentage4GSeconds": "TIME_PERCENTAGE_4G_SECONDS",
    "time_percentage_4G_measurements": "TIME_PERCENTAGE_4G_MEASUREMENTS",
    "tCob5GNsa": "TIME_PERCENTAGE_5G_NSA",
    "timePercentage5GNsaSeconds": "TIME_PERCENTAGE_5G_NSA_SECONDS",
    "time_percentage_5G_NSA_measurements": "TIME_PERCENTAGE_5G_NSA_MEASUREMENTS",
    "timePercentageTotalSeconds": "TIME_PERCENTAGE_TOTAL_SECONDS",
    "perdidaPaquetes3G": "PACKET_LOSS_3G",
    "paquetesPerdidos3G": "LOST_PACKET_3G",
    "paquetesTramsitidos3G": "PACKET_TRANSMITTED_3G",
    "packet_loss_3G_measurements": "PACKET_LOSS_3G_MEASUREMENTS",
    "perdidaPaquetes4G": "PACKET_LOSS_4G",
    "paquetesPerdidos4G": "LOST_PACKET_4G",
    "paquetesTransmitidos4G": "PACKET_TRANSMITTED_4G",
    "packet_loss_4G_measurements": "PACKET_LOSS_4G_MEASUREMENTS",
    "perdidaPaquetes5GNsa": "PACKET_LOSS_5G_NSA",
    "paquetesPerdidos5GNsa": "LOST_PACKET_5G_NSA",
    "paquetesTramsitidos5GNsa": "PACKET_TRANSMITTED_5G_NSA",
    "packet_loss_5G_NSA_measurements": "PACKET_LOSS_5G_NSA_MEASUREMENTS",
}
LEGACY_COLUMNS = list(JSON_TO_LEGACY_COLUMNS.values())


def decrypt_osiptel_token(encrypted_token: str) -> str:
    import base64

    raw = base64.b64decode(encrypted_token)
    decrypted = AES.new(OSIPTEL_AES_KEY, AES.MODE_CBC, OSIPTEL_AES_IV).decrypt(raw)
    return unpad(decrypted, AES.block_size).decode("utf-8")


def make_session() -> tuple[requests.Session, dict[str, str]]:
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE_URL}/",
        "Origin": BASE_URL,
        "User-Agent": user_agent,
    }
    session = requests.Session()
    session.verify = False

    print("Solicitando token de OSIPTEL...")
    info = session.post(OSIPTEL_INFO_URL, headers=headers, timeout=30)
    info.raise_for_status()
    auth = info.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise RuntimeError("OSIPTEL /info no devolvio header Authorization Bearer.")

    token = decrypt_osiptel_token(auth.split(" ", 1)[1])
    headers["Authorization"] = f"Bearer {token}"
    print(f"  Token JWT obtenido ({len(token)} chars)")
    return session, headers


def write_json_dataset_as_legacy_csv(payload: object, dest: Path) -> int:
    if isinstance(payload, dict):
        rows = payload.get("data", [])
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []

    if not rows:
        raise RuntimeError("OSIPTEL no devolvio filas en la respuesta JSON.")

    df = pd.DataFrame(rows).rename(columns=JSON_TO_LEGACY_COLUMNS)
    for column in LEGACY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[LEGACY_COLUMNS]
    df.to_csv(dest, index=False, sep=";", encoding="utf-8")
    return len(df)


def download_year_csv(year: int) -> Path:
    dest = ROOT / "data" / "raw" / f"dataset_{year}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)

    session, headers = make_session()
    print(f"Descargando dataset {year} desde OSIPTEL...")
    response = session.get(OSIPTEL_URL, params={"anio": year}, headers=headers, timeout=180)
    response.raise_for_status()

    if response.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extract("dataset.csv", path=dest.parent)
            (dest.parent / "dataset.csv").rename(dest)
        rows_msg = "ZIP"
    else:
        rows = write_json_dataset_as_legacy_csv(response.json(), dest)
        rows_msg = f"{rows:,} filas JSON"

    print(f"  Guardado: {dest.name} ({rows_msg}, {dest.stat().st_size / 1_048_576:.1f} MB)")
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
    print(f"  osiptel_series_final.csv: {len(final):,} filas -> {out_final}")

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
