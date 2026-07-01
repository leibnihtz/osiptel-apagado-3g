from __future__ import annotations

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def _yearmonth_to_date(ym: pd.Series) -> pd.Series:
    """Convierte int YYYYMM -> datetime (primer dia del mes)."""
    ym = ym.astype(int)
    y = ym // 100
    m = ym % 100
    return pd.to_datetime({"year": y, "month": m, "day": 1})


def plot_district_timeline(
    df: pd.DataFrame,
    title: str,
    breakpoint_yearmonth: int | None = None,
    save_path: Path | None = None,
) -> None:
    """
    Grafico timeline:
    - Eje izq: DL 3G y DL 4G (Mbps)
    - Eje der: 3G DL measurements (barras)
    - Eje X: fechas mensuales reales
    Además:
    - reindex mensual para evitar "puentes" por meses faltantes.
    """

    required = ["YEARMONTH", "AVERAGE_THROUGHPUT_DOWNLOAD_3G", "THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS"]
    for c in required:
        if c not in df.columns:
            raise KeyError(f"Falta columna requerida para plot: {c}")

    d = df.copy()
    d["DATE"] = _yearmonth_to_date(d["YEARMONTH"])
    d = d.sort_values("DATE")

    # Reindex mensual completo (para que el gráfico no conecte saltando meses)
    full_idx = pd.date_range(d["DATE"].min(), d["DATE"].max(), freq="MS")
    d = d.set_index("DATE").reindex(full_idx)

    # Si no existe 4G, no lo graficamos
    has_4g = "AVERAGE_THROUGHPUT_DOWNLOAD_4G" in d.columns

    # Rellenos:
    # - Throughput: NaN -> 0 (porque OSIPTEL vacío -> 0 en tu criterio)
    d["AVERAGE_THROUGHPUT_DOWNLOAD_3G"] = d["AVERAGE_THROUGHPUT_DOWNLOAD_3G"].fillna(0)
    if has_4g:
        d["AVERAGE_THROUGHPUT_DOWNLOAD_4G"] = d["AVERAGE_THROUGHPUT_DOWNLOAD_4G"].fillna(0)

    # - Measurements: NaN -> 0
    d["THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS"] = d["THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS"].fillna(0)

    x = d.index

    fig, ax1 = plt.subplots()

    # Lineas throughput (eje izquierdo)
    ax1.plot(x, d["AVERAGE_THROUGHPUT_DOWNLOAD_3G"], marker="o", linewidth=1, label="DL 3G (Mbps)")
    if has_4g:
        ax1.plot(x, d["AVERAGE_THROUGHPUT_DOWNLOAD_4G"], marker="o", linewidth=1, label="DL 4G (Mbps)")

    ax1.set_xlabel("Mes")
    ax1.set_ylabel("Throughput (Mbps)")
    ax1.set_title(title)

    # Barras measurements (eje derecho)
    #ax2 = ax1.twinx()
    #ax2.bar(x, d["THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS"], alpha=0.3, label="3G DL measurements")
    #ax2.set_ylabel("3G DL measurements")

    # Línea vertical breakpoint (si se provee)
    if breakpoint_yearmonth is not None:
        bp_date = _yearmonth_to_date(pd.Series([breakpoint_yearmonth])).iloc[0]
        ax1.axvline(bp_date, linewidth=2, linestyle="--", color="red", label=f"Breakpoint {breakpoint_yearmonth}")

    # Ticks: uno cada 2 meses para legibilidad
    step = 2
    ax1.set_xticks(x[::step])
    ax1.set_xticklabels([dt.strftime("%Y-%m") for dt in x[::step]], rotation=45, ha="right")

    # Leyenda combinada
    l1, lab1 = ax1.get_legend_handles_labels()
    #l2, lab2 = ax2.get_legend_handles_labels()
    #ax1.legend(l1 + l2, lab1 + lab2, loc="upper left")
    ax1.legend(l1 , lab1 , loc="upper left")
    fig.tight_layout()

    if save_path is not None:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150)

    # En batch no queremos abrir ventanas
    if save_path is None:
        plt.show()
    else:
        plt.close(fig)
