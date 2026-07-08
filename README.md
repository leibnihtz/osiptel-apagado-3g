# Apagado 3G de Movistar en Perú — Análisis distrital del refarming

Detecta los distritos donde Movistar desactivó el 3G y analiza si la transición al 4G mejoró la calidad del internet móvil.

**Datos:** [OSIPTEL — Checa tu Internet Móvil](https://checatuinternetmovil.osiptel.gob.pe)  
**Actualización:** automática el día 1 de cada mes vía GitHub Actions  
**Python:** 3.11 (requerido; pinned en CI)  
**Visualización:** [ObservableHQ](https://observablehq.com/d/42e2b1280524610e)  
**Autor:** Leibnihtz Ayamamani-Choque · [@leibnihtz](https://github.com/leibnihtz)

---

## ¿Qué hace este proyecto?

1. Descarga el dataset mensual de OSIPTEL (calidad de internet móvil por distrito)
2. Detecta distritos con **apagado 3G confirmado** usando la regla: throughput y mediciones 3G en cero de forma sostenida
3. Calcula métricas de mejora 4G: velocidad, latencia, cobertura y pérdida de paquetes antes y después del apagado
4. Genera archivos CSV y GeoJSON listos para visualizar en ObservableHQ
5. Hace git push automático — ObservableHQ lee los datos actualizados sin intervención manual

---

## Regla de detección de apagado 3G

| Condición | Criterio |
|---|---|
| Mes 3G activo | `AVERAGE_THROUGHPUT_DOWNLOAD_3G > 0` y `THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS > 0` |
| Breakpoint | Primer mes donde ambos valores son 0, después de haber tenido meses activos |
| Confirmado | Breakpoint sostenido hasta el último mes disponible, con ≥ 10 meses activos previos |

---

## Métrica principal: delta 4G

```
delta_4g_download_mbps = post6_4g_download_mbps − pre6_4g_download_mbps
```

- **pre6:** promedio de los últimos 6 meses antes del breakpoint
- **post6:** promedio de los primeros 6 meses desde el breakpoint inclusive
- **composite_upgrade_score:** índice ponderado (DL 40%, latencia 25%, cobertura 15%, UL 15%, pérdida 5%)

---

## Estructura del repositorio

```
data/
  raw/               # CSVs históricos por año (2023–2026)
  geo/               # GeoJSON simplificado de distritos del Perú
outputs/
  tables/            # shutdown_confirmed.csv + dataset filtrado
  observable/data/   # Archivos listos para ObservableHQ
scripts/
  download.py        # Entrypoint del pipeline mensual
  build_observable_outputs.py  # Genera CSV y GeoJSON para Observable
src/portalosiptel3g/ # Paquete Python: io, cleaning, features, detection
.github/workflows/
  pipeline.yml       # GitHub Actions: cron mensual
```

---

## Outputs principales

| Archivo | Descripción |
|---|---|
| `outputs/tables/shutdown_confirmed.csv` | Distritos con apagado 3G confirmado y mes de breakpoint |
| `outputs/tables/dataset_2023_2025_shutdown_districts.csv` | Serie mensual completa para esos distritos |
| `outputs/observable/data/observable_4g_upgrade_summary_with_ubigeo.csv` | Resumen de métricas pre/post por distrito con UBIGEO |
| `outputs/observable/data/observable_shutdown_timeseries.csv` | Serie temporal con `relative_month` para visualización |
| `outputs/observable/data/observable_all_districts_with_upgrade_simplified.geojson` | Mapa de todos los distritos del Perú con métricas inyectadas |
| `outputs/observable/data/observable_4g_upgrade_districts.geojson` | Mapa solo de distritos con apagado confirmado |

---

## Correr el pipeline localmente

```bash
pip install -r requirements.txt
pip install -e .
python scripts/download.py
```

---

## Pipeline automático (GitHub Actions)

El workflow `.github/workflows/pipeline.yml` corre el día 1 de cada mes y:

1. Descarga el dataset del año en curso desde la API de OSIPTEL
2. Ejecuta el pipeline de detección
3. Regenera los outputs de Observable
4. Hace commit y push automático al repositorio

Para correrlo manualmente: pestaña **Actions** → **OSIPTEL Pipeline** → **Run workflow**
