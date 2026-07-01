import argparse
from pathlib import Path
import logging
from portalosiptel3g.io import read_and_concat


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="portalosiptel3g",
        description="Herramienta para deteccion de apagado 3G (refarming) por distrito usando datasets OSIPTEL 2023-2025",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="Lee y une CSVs OSIPTEL (paso inicial del pipeline)")
    d.add_argument("--data-dir", required=True, help="Directorio con dataset_*.csv (ej: data/raw)")
    d.add_argument("--pattern", default="dataset_*.csv", help="Patron de archivos (default: dataset_*.csv)")
    d.add_argument("--carrier", default="MOVISTAR", help="Operador (default: MOVISTAR)")
    d.add_argument("--out-dir", default="outputs/tables", help="Directorio salida (default: outputs/tables)")
    d.add_argument(
    "--write-filtered",
    action="store_true",
    help="Genera dataset 2023-2025 filtrado por distritos SHUTDOWN_CONFIRMED",
    )
    d.add_argument(
    "--log-dir",
    default=None,
    help="Directorio para logs (opcional). Ej: outputs/logs",
    )

    i = sub.add_parser("inspect", help="Inspecciona un distrito y muestra resumen (sin graficos por ahora)")
    i.add_argument("--data-dir", required=True, help="Directorio con dataset_*.csv (ej: data/raw)")
    i.add_argument("--pattern", default="dataset_*.csv", help="Patron de archivos (default: dataset_*.csv)")
    i.add_argument("--carrier", default="MOVISTAR", help="Operador (default: MOVISTAR)")

    i.add_argument("--adm1", default=None, help="Departamento (opcional)")
    i.add_argument("--adm2", default=None, help="Provincia (opcional)")
    i.add_argument("--adm3", required=True, help="Distrito (obligatorio, exact match por ahora)")
    i.add_argument("--save-plot", default=None, help="Ruta para guardar PNG (opcional). Ej: outputs/tables/arequipa_jlbustamante.png")

    b = sub.add_parser("plot-batch", help="Genera graficos PNG para distritos SHUTDOWN_CONFIRMED (batch)")
    b.add_argument("--data-dir", required=True, help="Directorio con dataset_*.csv (ej: data/raw)")
    b.add_argument("--pattern", default="dataset_*.csv", help="Patron de archivos (default: dataset_*.csv)")
    b.add_argument("--core-csv", default="outputs/tables/shutdown_confirmed.csv", help="Ruta al output core")
    b.add_argument("--carrier", default="MOVISTAR", help="Operador (default: MOVISTAR)")
    b.add_argument("--out-dir", default="outputs/reports/plots", help="Directorio salida PNGs")
    b.add_argument("--limit", type=int, default=0, help="Limite de distritos (0 = todos)")


    return p


def cmd_detect(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    from portalosiptel3g.logging_config import setup_logging
    setup_logging(args.log_dir)
    log = logging.getLogger(__name__)
    from portalosiptel3g.cleaning import clean_minimal
    from portalosiptel3g.features import add_yearmonth, add_3g_flags
    from portalosiptel3g.detection import detect_shutdown_confirmed
    from portalosiptel3g.export import write_outputs
    

    df = read_and_concat(data_dir, pattern=args.pattern)
    df = clean_minimal(df)
    df = add_yearmonth(df)
    df = add_3g_flags(df)

    carrier = args.carrier.upper()
    core = detect_shutdown_confirmed(df, carrier=carrier)

    out_dir = Path(args.out_dir)
    #path = write_core_table(core, out_dir=out_dir)
    outputs = write_outputs(
        df_all=df,
        core_df=core,
        out_dir=out_dir,
        write_filtered=args.write_filtered,
    )

    log.info("Pipeline ejecutado correctamente")
    log.info("Carrier=%s", carrier)
    log.info("Distritos SHUTDOWN_CONFIRMED=%d", len(core))
    for k, v in outputs.items():
        log.info("Output %s: %s", k, v)

    # Preview de los primeros 10
    if len(core) > 0:
        print(core.head(10).to_string(index=False))

    return 0

def cmd_inspect(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)

    from portalosiptel3g.cleaning import clean_minimal
    from portalosiptel3g.features import add_yearmonth, add_3g_flags

    df = read_and_concat(data_dir, pattern=args.pattern)
    df = clean_minimal(df)
    df = add_yearmonth(df)
    df = add_3g_flags(df)

    carrier = args.carrier.upper()
    d = df[df["NETWORK_CARRIER"] == carrier].copy()
    if d.empty:
        print(f"No hay filas para carrier={carrier}")
        return 1

    # Filtro por distrito (exact match por ahora)
    if args.adm1 is not None:
        d = d[d["ADM_LEVEL_1_NAME"] == args.adm1]
    if args.adm2 is not None:
        d = d[d["ADM_LEVEL_2_NAME"] == args.adm2]

    d = d[d["ADM_LEVEL_3_NAME"] == args.adm3]

    if d.empty:
        print("No se encontro el distrito con esos filtros.")
        print("Tips:")
        print("- Verifica mayus/minus y espacios (por ahora es exact match).")
        print("- Prueba solo con --adm3 sin adm1/adm2 si no estas seguro.")
        return 2

    d = d.sort_values("YEARMONTH")

    # Resumen
    ym_min = int(d["YEARMONTH"].min())
    ym_max = int(d["YEARMONTH"].max())
    active_months = int(d["IS_3G_ACTIVE_MONTH"].sum())
    zero_months = int(d["IS_3G_ZERO_MONTH"].sum())

    # Breakpoint "candidato": primer mes ZERO luego de haber visto ACTIVE
    seen_active = False
    breakpoint = None
    for _, r in d.iterrows():
        if bool(r["IS_3G_ACTIVE_MONTH"]):
            seen_active = True
        if seen_active and bool(r["IS_3G_ZERO_MONTH"]):
            breakpoint = int(r["YEARMONTH"])
            break

    print("OK: inspect (sin graficos)")
    print("Carrier:", carrier)
    print("ADM1:", d["ADM_LEVEL_1_NAME"].iloc[0])
    print("ADM2:", d["ADM_LEVEL_2_NAME"].iloc[0])
    print("ADM3:", d["ADM_LEVEL_3_NAME"].iloc[0])
    print("YEARMONTH rango:", ym_min, "->", ym_max)
    print("Meses 3G ACTIVE:", active_months)
    print("Meses 3G ZERO:", zero_months)
    print("Breakpoint candidato:", breakpoint)

    # Preview de timeline (solo columnas clave)
    cols = ["YEARMONTH", "AVERAGE_THROUGHPUT_DOWNLOAD_3G", "THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS", "IS_3G_ACTIVE_MONTH", "IS_3G_ZERO_MONTH"]
    cols = [c for c in cols if c in d.columns]
    print("\nTimeline preview (ultimos 24 meses o menos):")
    print(d[cols].tail(24).to_string(index=False))

    # Plot
    from portalosiptel3g.plotting import plot_district_timeline
    from pathlib import Path as _Path

    save_path = _Path(args.save_plot) if args.save_plot else None
    title = f"{carrier} | {d['ADM_LEVEL_1_NAME'].iloc[0]} / {d['ADM_LEVEL_2_NAME'].iloc[0]} / {d['ADM_LEVEL_3_NAME'].iloc[0]}"
    plot_district_timeline(d, title=title, breakpoint_yearmonth=breakpoint, save_path=save_path)
    
    
    
    return 0

def _safe_name(s: str) -> str:
    """Convierte texto a nombre seguro para archivo."""
    s = str(s).strip().replace(" ", "_")
    # quita caracteres problemáticos en Windows
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(ch, "")
    return s


def cmd_plot_batch(args: argparse.Namespace) -> int:
    from pathlib import Path
    import logging
    import pandas as pd

    from portalosiptel3g.logging_config import setup_logging
    from portalosiptel3g.cleaning import clean_minimal
    from portalosiptel3g.features import add_yearmonth, add_3g_flags
    from portalosiptel3g.plotting import plot_district_timeline
    from portalosiptel3g.io import read_and_concat

    setup_logging(None)
    log = logging.getLogger(__name__)

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    carrier = args.carrier.upper()

    # 1) Cargar core (shutdown_confirmed.csv)
    core_path = Path(args.core_csv)
    if not core_path.exists():
        log.error("No existe core-csv: %s", core_path)
        return 2

    core = pd.read_csv(core_path, dtype=str)
    if core.empty:
        log.error("Core CSV vacio: %s", core_path)
        return 3

    core = core[core["NETWORK_CARRIER"].str.upper() == carrier]
    if core.empty:
        log.error("No hay distritos confirmados en core para carrier=%s", carrier)
        return 4

    if args.limit and args.limit > 0:
        core = core.head(args.limit)

    log.info("Distritos a graficar (carrier=%s): %d", carrier, len(core))

    # 2) Cargar dataset completo (una sola vez)
    df = read_and_concat(data_dir, pattern=args.pattern)
    df = clean_minimal(df)
    df = add_yearmonth(df)
    df = add_3g_flags(df)

    # Filtra por carrier para acelerar
    df = df[df["NETWORK_CARRIER"] == carrier].copy()
    if df.empty:
        log.error("No hay filas en dataset para carrier=%s", carrier)
        return 5

    # 3) Iterar por distritos confirmados y generar PNG
    ok = 0
    missing = 0

    for _, r in core.iterrows():
        adm1 = r["ADM_LEVEL_1_NAME"]
        adm2 = r["ADM_LEVEL_2_NAME"]
        adm3 = r["ADM_LEVEL_3_NAME"]
        bp = int(r["BREAKPOINT_YEARMONTH"]) if "BREAKPOINT_YEARMONTH" in r and str(r["BREAKPOINT_YEARMONTH"]).strip() else None

        d = df[
            (df["ADM_LEVEL_1_NAME"] == adm1) &
            (df["ADM_LEVEL_2_NAME"] == adm2) &
            (df["ADM_LEVEL_3_NAME"] == adm3)
        ].copy()

        if d.empty:
            missing += 1
            log.warning("No encontre data para: %s / %s / %s", adm1, adm2, adm3)
            continue

        d = d.sort_values("YEARMONTH")

        fname = f"{_safe_name(adm1)}__{_safe_name(adm2)}__{_safe_name(adm3)}__{carrier}.png"
        save_path = out_dir / fname

        title = f"{carrier} | {adm1} / {adm2} / {adm3}"

        try:
            plot_district_timeline(d, title=title, breakpoint_yearmonth=bp, save_path=save_path)
            ok += 1
        except Exception as e:
            log.warning("Fallo plot para %s / %s / %s: %s", adm1, adm2, adm3, e)

    log.info("Batch terminado. Generados=%d, No_encontrados=%d", ok, missing)
    log.info("Carpeta de salida: %s", out_dir)
    return 0



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "detect":
        raise SystemExit(cmd_detect(args))
    
    if args.cmd == "inspect":
        raise SystemExit(cmd_inspect(args))
    if args.cmd == "plot-batch":
        raise SystemExit(cmd_plot_batch(args))
