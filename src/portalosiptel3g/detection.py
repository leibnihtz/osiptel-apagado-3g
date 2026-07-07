import pandas as pd


KEYS = ["ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME", "NETWORK_CARRIER"]

# Meses con tráfico 3G activo requeridos antes del breakpoint (acumulados, no consecutivos).
MIN_ACTIVE_MONTHS_PRE = 10


def detect_shutdown_confirmed(df: pd.DataFrame, carrier: str) -> pd.DataFrame:
    d = df[df["NETWORK_CARRIER"] == carrier.upper()].copy()
    if d.empty:
        raise ValueError(f"No hay data para carrier={carrier}")

    # Último mes global disponible para ese carrier
    last_ym = int(d["YEARMONTH"].max())
    months_sorted = sorted(d["YEARMONTH"].unique().tolist())

    rows = []

    for key, g in d.groupby(KEYS, dropna=False):
        g = g.sort_values("YEARMONTH")
        months_present = set(g["YEARMONTH"].tolist())

        # requisito: alguna vez ACTIVE
        if not bool(g["IS_3G_ACTIVE_MONTH"].any()):
            continue  # no es candidato a "apagado" por nuestra definición

        # breakpoint: primer mes ZERO que ocurre despues de haber visto ACTIVE
        seen_active = False
        breakpoint = None
        for _, r in g.iterrows():
            if bool(r["IS_3G_ACTIVE_MONTH"]):
                seen_active = True
            if seen_active and bool(r["IS_3G_ZERO_MONTH"]):
                breakpoint = int(r["YEARMONTH"])
                break

        if breakpoint is None:
            continue

        pre = g[g["YEARMONTH"] < breakpoint]
        active_pre_months = int(pre["IS_3G_ACTIVE_MONTH"].sum())
        if active_pre_months < MIN_ACTIVE_MONTHS_PRE:
            continue

        # confirmación: desde breakpoint hasta last_ym:
        tail_months = [m for m in months_sorted if m >= breakpoint and m <= last_ym]

        # si hay huecos de meses, no confirmamos
        if any(m not in months_present for m in tail_months):
            continue

        g_tail = g[g["YEARMONTH"].isin(tail_months)]
        if bool((~g_tail["IS_3G_ZERO_MONTH"]).any()):
            continue

        adm1, adm2, adm3, carr = key
        rows.append({
            "ADM_LEVEL_1_NAME": adm1,
            "ADM_LEVEL_2_NAME": adm2,
            "ADM_LEVEL_3_NAME": adm3,
            "NETWORK_CARRIER": carr,
            "BREAKPOINT_YEARMONTH": breakpoint,
            "LAST_YEARMONTH_AVAILABLE": last_ym,
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out = out.sort_values(["BREAKPOINT_YEARMONTH", "ADM_LEVEL_1_NAME", "ADM_LEVEL_2_NAME", "ADM_LEVEL_3_NAME"])
    return out
