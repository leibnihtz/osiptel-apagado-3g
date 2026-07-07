# AUDIT — Pipeline OSIPTEL 3G Shutdown

Fotografía del estado actual del repositorio para paper IEEE LATINCOM 2026.
Generado el 2026-07-07. Toda afirmación cita el archivo y línea donde está implementado.
Nada se rellena con suposiciones; lo que no está implementado se marca **[GAP]** o **[AMBIGUO]**.

---

## 1. Inventario del pipeline

### Scripts y orden de ejecución

```
scripts/download.py          ← entrypoint único (GitHub Actions lo llama)
  └─ io.read_and_concat()          src/portalosiptel3g/io.py:22
  └─ cleaning.clean_minimal()      src/portalosiptel3g/cleaning.py:17
  └─ features.add_yearmonth()      src/portalosiptel3g/features.py:4
  └─ features.add_3g_flags()       src/portalosiptel3g/features.py:10
  └─ detection.detect_shutdown_confirmed()  src/portalosiptel3g/detection.py:10
  └─ (filtro + guardado CSVs)      scripts/download.py:186-197
  └─ subprocess → build_observable_outputs.py  scripts/download.py:201-211

scripts/build_observable_outputs.py
  └─ build_summary()               línea 89
  └─ build_timeseries()            línea 190
  └─ inject_geo_metrics()          línea 226

scripts/convert_departments_shapefile.py   ← script manual, NO en Actions
  Lee: Limite_Departamental/*.shp
  Escribe: outputs/observable/data/observable_departments_inei_2023_simplified.geojson

scripts/audit_stats.py            ← solo lectura, no modifica pipeline
```

### Diagrama de flujo

```
data/raw/dataset_2023.csv
data/raw/dataset_2024.csv       ──→ read_and_concat()
data/raw/dataset_2025.csv                │
data/raw/dataset_2026.csv                ▼
                                  clean_minimal()
                                         │
                                  add_yearmonth() + add_3g_flags()
                                         │
                                  detect_shutdown_confirmed(MOVISTAR)
                                         │
                              ┌──────────┴──────────┐
                              ▼                      ▼
                  shutdown_confirmed.csv    dataset_2023_2025_shutdown_districts.csv
                  (86 filas)               (3 526 filas, todos los meses de los 86)
                              │
                              ▼
                  build_observable_outputs.py
                              │
               ┌──────────────┼──────────────┐
               ▼              ▼               ▼
   observable_4g_upgrade_   observable_all_  observable_shutdown_
   summary[_with_ubigeo].csv districts_...   timeseries.csv
   observable_4g_upgrade_   .geojson
   districts.geojson
```

### GitHub Actions

- **Archivo:** `.github/workflows/pipeline.yml`
- **Frecuencia:** día 1 de cada mes a las 06:00 UTC (01:00 hora Perú). Disparo manual disponible.
- **Python:** 3.11 (pinned en `setup-python@v5`).
- **Pasos:** checkout → pip install -r requirements.txt → pip install -e . → `python scripts/download.py` → git add + commit + push.
- **Archivos que el bot commitea:**
  - `osiptel_series_final.csv` (raíz del repo)
  - `data/raw/dataset_${YEAR}.csv`
  - `data/geo/peru_districts_simplified.geojson` ← **[AMBIGUO]**: el pipeline no modifica este archivo; incluyendo en `git add` no tiene efecto práctico pero puede confundir.
  - `outputs/tables/dataset_2023_2025_shutdown_districts.csv`
  - `outputs/tables/shutdown_confirmed.csv`
  - `outputs/observable/data/` (directorio completo)

---

## 2. Datos de entrada

### Cobertura temporal

| Campo | Valor |
|---|---|
| Primer YEARMONTH en raw | **202301** (enero 2023) |
| Último YEARMONTH en raw | **202605** (mayo 2026) |
| Meses distintos en el dataset | **41** |

Fuente: `scripts/audit_stats.py` corrido sobre `data/raw/dataset_*.csv`.

### Conteo de distritos

| Universo | N |
|---|---|
| Distritos Movistar únicos en los raw CSVs | **1 920** |
| Distritos en GeoJSON `peru_districts_simplified.geojson` (todos carriers/todos) | **1 891** (observable notebook, Celda 2) |
| Distritos confirmados con apagado 3G | **86** |
| Confirmados con ≥ 3 meses post-breakpoint | **68** |

**Nota:** El GeoJSON de distritos (`data/geo/`) es un archivo preexistente no generado por el pipeline. La diferencia 1920 vs 1891 refleja que el GeoJSON cubre el universo geopolítico peruano mientras que el raw de OSIPTEL solo incluye distritos con medición reportada para MOVISTAR.

### Columnas de OSIPTEL usadas en el pipeline

| Columna OSIPTEL | Uso |
|---|---|
| `AÑO`, `MES` | Construir `YEARMONTH` (`features.py:6`) |
| `ADM_LEVEL_1/2/3_NAME` | Clave de agrupación distrito |
| `NETWORK_CARRIER` | Filtro MOVISTAR (`download.py:36`, `detection.py:11`) |
| `AVERAGE_THROUGHPUT_DOWNLOAD_3G` | Flag `IS_3G_ACTIVE_MONTH` y `IS_3G_ZERO_MONTH` (`features.py:20-21`) |
| `THROUGHPUT_DOWNLOAD_3G_MEASUREMENTS` | Ídem |
| `AVERAGE_THROUGHPUT_DOWNLOAD_4G` | Métrica principal pre/post (`build_observable_outputs.py:118-119`) |
| `THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS` | Reportado en summary; NO usado como peso en promedios |
| `AVERAGE_THROUGHPUT_UPLOAD_4G` | Métrica secundaria |
| `AVERAGE_LATENCY_4G` | Métrica secundaria |
| `TIME_PERCENTAGE_4G` | Métrica secundaria |
| `PACKET_LOSS_4G` | Métrica secundaria (peso 5% en score) |

Columnas completas mapeadas en `download.py:43-90` (47 campos totales).

### Meses faltantes vs valores en cero

**[GAP]** — Son **indistinguibles** después del proceso de limpieza.

`clean_minimal()` (`cleaning.py:48-49`) reemplaza string vacío por 0 en todas las columnas KPI antes de que se genere `IS_3G_ZERO_MONTH`. Una fila ausente del CSV fuente (mes sin reporte) y una fila presente con throughput = 0 producen el mismo resultado: `IS_3G_ZERO_MONTH = True`. El pipeline no tiene mecanismo para distinguir "OSIPTEL no reportó ese mes" de "reportó 0 Mbps de 3G".

Implicación para el paper: la condición de confirmación (todos los meses desde el breakpoint son ZERO sin huecos, `detection.py:47-56`) protege contra falsos positivos por meses ausentes, pero no permite distinguir en el texto si el 3G bajó a cero porque se apagó o porque no hubo medición ese mes.

### Estabilidad del dataset entre años

| Transición | Desaparecen | Aparecen |
|---|---|---|
| dataset_2023 → dataset_2024 | 0 | 0 |
| dataset_2024 → dataset_2025 | 0 | **44** |
| dataset_2025 → dataset_2026 | **50** | 0 |

Los 44 distritos que aparecen en 2025 y los 50 que desaparecen en 2026 (parcialmente solapados) son distritos con reporte intermitente. Ninguno de los 86 confirmados tiene gaps en su serie (verificado: `audit_stats.py` → "gap_count=0").

---

## 3. Parámetros y umbrales

| # | Valor | Descripción | Archivo | Línea | Estado |
|---|---|---|---|---|---|
| 1 | `MIN_ACTIVE_MONTHS_PRE = 10` | Meses 3G activos (acumulados, no consecutivos) requeridos antes del breakpoint | `src/portalosiptel3g/detection.py` | 7 | **Constante nombrada** |
| 2 | `6` | Ventana pre-shutdown: `pre_all.tail(6)` | `scripts/build_observable_outputs.py` | 115 | **Hardcoded** |
| 3 | `6` | Ventana post-shutdown: `post_all.head(6)` | `scripts/build_observable_outputs.py` | 116 | **Hardcoded** |
| 4 | `3` | Mínimo de meses post para incluir en análisis | `outputs/observable/observable_notebook_apagado3g_upgrade4g.md` | Celda 3 (`filteredSummary`) | **Hardcoded en notebook** |
| 5 | `0.40` | Peso descarga 4G en composite score | `scripts/build_observable_outputs.py` | 138 | **Hardcoded** |
| 6 | `0.15` | Peso upload 4G en composite score | `scripts/build_observable_outputs.py` | 139 | **Hardcoded** |
| 7 | `0.25` | Peso latencia en composite score | `scripts/build_observable_outputs.py` | 140 | **Hardcoded** |
| 8 | `0.15` | Peso tiempo en 4G en composite score | `scripts/build_observable_outputs.py` | 141 | **Hardcoded** |
| 9 | `0.05` | Peso pérdida de paquetes en composite score | `scripts/build_observable_outputs.py` | 142 | **Hardcoded** |
| 10 | `12` | Ventana de meses relativos en event-study heatmap | notebook Celda 5B | `relative_month >= -12 and <= 12` | **Hardcoded en notebook** |
| 11 | `40` | Top N distritos en event-study heatmap | notebook Celda 5B | `eventTopN = 40` | **Hardcoded en notebook** |
| 12 | `0.01` | Tolerancia de simplificación geométrica (grados, ≈1 km) | `scripts/convert_departments_shapefile.py` | 12 | **Hardcoded** |
| 13 | `"MOVISTAR"` | Carrier analizado | `scripts/download.py` | 36 | **Hardcoded como constante de módulo** |

---

## 4. Cálculo de métricas

### ¿Promedio ponderado o simple?

**Promedio simple de promedios mensuales.** La función `mean_or_na()` (`build_observable_outputs.py:56-59`) usa `frame[column].mean(skipna=True)` sobre los hasta 6 meses de la ventana. No pondera por `THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS`.

**[GAP]** — Un mes con 5 mediciones tiene el mismo peso que uno con 500 000. Dado que la distribución de mediciones es muy amplia (ver abajo), esto introduce varianza no controlada en los promedios mensuales de distritos pequeños.

### Distribución de mediciones por distrito-mes (ventana pre/post 6 meses, 86 confirmados)

| Estadístico | THROUGHPUT_DOWNLOAD_4G_MEASUREMENTS |
|---|---|
| n district-month | 939 |
| mínimo | 0 |
| p25 | 20 806 |
| mediana | 40 744 |
| p75 | 81 318 |
| máximo | 414 207 |
| Filas con 0 mediciones | **8 (0.9%)** |

Las 8 filas con 0 mediciones 4G dentro de la ventana de análisis son meses donde `AVERAGE_THROUGHPUT_DOWNLOAD_4G = 0` (sin 4G medible). Contribuyen con 0 al promedio mensual, distorsionando el baseline o el post.

### Fórmulas exactas

**`delta_4g_download_mbps`** (`build_observable_outputs.py:161`):
```
post6_mean_DL - pre6_mean_DL
donde:
  pre6_mean_DL  = mean(AVERAGE_THROUGHPUT_DOWNLOAD_4G, últimos 6 meses antes del breakpoint)
  post6_mean_DL = mean(AVERAGE_THROUGHPUT_DOWNLOAD_4G, primeros N meses desde breakpoint, N ≤ 6)
```

**`delta_4g_latency_ms`** (`build_observable_outputs.py:169`):
```
post6_mean_latency - pre6_mean_latency
(negativo = mejora)
```

**`composite_upgrade_score`** (`build_observable_outputs.py:135-147`):
```
score = Σ(value_i × weight_i) / Σ(weight_i para los i con valor no-NaN)

donde:
  dl_pct      = post_DL / pre_DL - 1             peso 0.40
  ul_pct      = post_UL / pre_UL - 1             peso 0.15
  latency_pct = pre_lat / post_lat - 1           peso 0.25  (mejora si post < pre)
  time_pp/100 = (post_time% - pre_time%) / 100   peso 0.15
  loss_pct    = pre_loss / post_loss - 1         peso 0.05
```

El denominador se ajusta si alguna métrica es NaN (normalización implícita sobre pesos disponibles).

---

## 5. Estadísticas descriptivas

### Los 86 confirmados — por departamento

| Departamento | N |
|---|---|
| Lima | 22 |
| Arequipa | 11 |
| Ica | 10 |
| La Libertad | 8 |
| Cusco | 8 |
| Junin | 6 |
| Puno | 6 |
| Lambayeque | 4 |
| Callao | 3 |
| Piura | 3 |
| Ancash | 2 |
| Tacna | 1 |
| Ayacucho | 1 |
| Tumbes | 1 |

**Nota:** Lima + Arequipa + Ica = 43/86 (50%). El apagado está fuertemente concentrado en la costa.

### Los 86 — distribución del mes de breakpoint

| YEARMONTH | N | | YEARMONTH | N |
|---|---|---|---|---|
| 202405 | 1 | | 202509 | 5 |
| 202406 | 5 | | 202510 | 3 |
| 202410 | 6 | | 202511 | 6 |
| 202411 | 6 | | 202512 | 10 |
| 202412 | **13** | | 202601 | 1 |
| 202501 | 4 | | 202602 | 4 |
| 202504 | 1 | | 202604 | 6 |
| 202505 | 1 | | 202605 | **12** |
| 202507 | 1 | | | |
| 202508 | 1 | | | |

El 58% de los apagados (50/86) ocurrió entre octubre 2024 y enero 2025 o en los últimos meses disponibles (dic 2025 – may 2026). Los breakpoints recientes (202604, 202605) tienen necesariamente pocos meses post.

### Los 68 filtrados (months_post ≥ 3) — delta descarga 4G

| Estadístico | Valor |
|---|---|
| n | 68 |
| media | **+0.997 Mbps** |
| mediana | **+0.993 Mbps** |
| desviación estándar | 1.016 Mbps |
| mínimo | −2.714 Mbps |
| máximo | +3.463 Mbps |
| n con delta > 0 | **62 (91.2%)** |

### Distribución de meses post disponibles (86 confirmados)

| months_post | N distritos |
|---|---|
| 1 | 12 |
| 2 | 6 |
| 4 | 4 |
| 5 | 1 |
| 6 | 10 |
| 7 | 6 |
| 8 | 3 |
| 9 | 5 |
| 10 | 1 |
| 11 | 1 |
| 13 | 1 |
| 14 | 1 |
| 17 | 4 |
| 18 | 13 |
| 19 | 6 |
| 20 | 6 |
| 24 | 5 |
| 25 | 1 |

18 distritos quedan fuera del análisis principal (months_post ∈ {1, 2}).

### Candidatos a grupo de control (distritos Movistar sin apagado)

| Criterio | N |
|---|---|
| 3G activo en los **41 meses** del dataset (control puro) | **101** |
| 3G activo en **≥ 10 meses** del dataset (control parcial) | **353** |
| Total distritos Movistar sin apagado confirmado | **1 834** |

101 distritos tienen 3G activo continuo durante todo el período — son los candidatos más limpios para un diseño diff-in-diff.

---

## 6. Reproducibilidad

### ¿Puede alguien regenerar los 86 desde los raw?

**Parcialmente.** El pipeline es determinista dado los CSVs raw. Los pasos son:

```bash
pip install -r requirements.txt
pip install -e .
# Con los raw CSVs ya en data/raw/:
python scripts/build_observable_outputs.py \
  --series outputs/tables/dataset_2023_2025_shutdown_districts.csv \
  --shutdown outputs/tables/shutdown_confirmed.csv
```

Para regenerar desde cero (incluyendo la detección de apagados):
```bash
python scripts/download.py   # descarga el año actual y corre el pipeline completo
```

### ¿Qué falta para reproducibilidad completa?

| Ítem | Estado |
|---|---|
| `requirements.txt` — dependencias del pipeline principal | Presente, pero **[GAP]**: no incluye `geopandas` ni `pyogrio`, requeridas por `convert_departments_shapefile.py` |
| Versión de Python | Pinned en GitHub Actions (3.11) pero **no documentada** en README ni requirements |
| Raw CSVs de OSIPTEL | **Versionados en el repo** (`data/raw/dataset_*.csv`) y commiteados por el bot mensualmente |
| Fuente de los raw CSVs | API pública de OSIPTEL: `checatuinternetmovil.osiptel.gob.pe/beta/api/Indicador/obtener-dataset`. La descarga requiere autenticación con token AES-256 cuyas claves están hardcodeadas en `download.py:40-41` |
| GeoJSON de distritos (`peru_districts_simplified.geojson`) | **[GAP]**: archivo preexistente, no hay script que lo regenere desde los shapefiles de `Limite_Distrital/`. Su origen no está documentado |
| Semilla aleatoria | No aplica — el pipeline es completamente determinista |

---

## 7. Inconsistencias conocidas

### 7.1. Comentario desactualizado en `detection.py` — CORREGIDO

- **Antes:** comentario `# NUEVA REGLA: debe haber al menos 3 meses ACTIVE` con umbral `< 10`.
- **Después (commit `1e4b395`):** constante `MIN_ACTIVE_MONTHS_PRE = 10` con comentario `"Meses con tráfico 3G activo requeridos antes del breakpoint (acumulados, no consecutivos)."`.

### 7.2. Título del notebook dice "post 6 meses" pero la ventana es variable

- **Notebook Celda 1:** *"La métrica principal es el cambio promedio de descarga 4G: post 6 meses − pre 6 meses."*
- **Implementación** (`build_observable_outputs.py:116`): `post6 = post_all.head(6)` — toma hasta 6, lo que haya disponible.
- Para distritos con breakpoint en 202604 o 202605 la ventana post es de 1–2 meses (excluidos por el filtro), y para breakpoints en 202601–202603 la ventana post tiene 4–5 meses.
- **[AMBIGUO]:** el texto del paper debe decir "hasta 6 meses post-breakpoint (mínimo 3 para inclusión en análisis)".

### 7.3. Nombre del archivo de serie sugiere cobertura hasta 2025

- Archivo: `outputs/tables/dataset_2023_2025_shutdown_districts.csv`
- Contiene datos hasta **202605 (mayo 2026)**.
- El nombre se fijó antes de que se incorporaran los datos de 2026. **[AMBIGUO]** para un lector externo.

### 7.4. El bot commitea `data/geo/peru_districts_simplified.geojson` sin modificarlo

- `pipeline.yml:41`: incluye `data/geo/peru_districts_simplified.geojson` en el `git add`.
- El pipeline nunca escribe en ese path. El `git diff --cached` lo ignorará, pero la intención es confusa.

### 7.5. `osiptel_series_final.csv` en raíz es duplicado de `outputs/tables/dataset_2023_2025_shutdown_districts.csv`

- `download.py:189-195` escribe el mismo DataFrame en dos rutas distintas.
- El bot commitea ambas. Son idénticas en contenido.

---

## 8. Riesgos para peer review

### R1 — Ausencia de grupo de control (riesgo ALTO)

La comparación pre/post captura la tendencia secular del 4G en todo el país (nuevos sitios, agregación de portadoras, mejoras de red generales). Sin un grupo de control (distritos sin apagado en el mismo período), el +0.993 Mbps mediano no es atribuible al refarming. Hay 101 distritos candidatos a control puro en los datos actuales. Un revisor de ComSoc muy probablemente rechazará el paper sin este análisis o exigirá major revision.

### R2 — Significancia estadística ausente (riesgo ALTO)

No hay test estadístico sobre el delta mediano. Con n=68 es viable un Wilcoxon signed-rank (pre vs post por distrito) y un bootstrap del IC 95% de la mediana. Sin p-value el paper no puede afirmar que la mejora es estadísticamente significativa.

### R3 — Promedio de promedios sin ponderar por mediciones (riesgo MEDIO)

`mean_or_na()` da el mismo peso a un mes con 5 mediciones que a uno con 400 000. El p25 de mediciones es 20 806, por lo que en la mayoría de casos el impacto es bajo, pero las 8 filas con 0 mediciones dentro de la ventana deberían excluirse o marcarse explícitamente.

### R4 — Detección basada en umbral exactamente cero (riesgo MEDIO)

`IS_3G_ZERO_MONTH` requiere `throughput == 0 AND measurements == 0`. Un distrito donde OSIPTEL reporta 0.001 Mbps de 3G (residual de handover) nunca dispara el criterio aunque operativamente el 3G esté apagado. El umbral exacto-cero puede ser correcto dado que OSIPTEL reporta cero cuando no hay tráfico, pero debe justificarse en el paper.

### R5 — Meses faltantes indistinguibles de ceros (riesgo MEDIO)

`clean_minimal()` convierte string vacío en 0 antes de generar los flags. Si OSIPTEL omite un mes en su reporte (fila ausente), el pipeline lo trata como si no hubiera 3G ese mes. La confirmación de shutdown exige que todos los meses desde el breakpoint estén presentes y sean ZERO, lo que protege contra falsos positivos pero no permite declarar en el paper que "ausencia de fila = cero confirmado".

### R6 — Carrier único (riesgo BAJO para LATINCOM, MEDIO para generalización)

El análisis solo cubre MOVISTAR. CLARO, ENTEL y BITEL no están incluidos. El paper debe delimitar explícitamente el alcance y no generalizar a "el mercado peruano".

### R7 — Concentración geográfica (riesgo BAJO)

50% de los 86 distritos están en Lima, Arequipa e Ica. El refarming puede reflejar estrategia de densificación en zonas urbanas de alta demanda, no un fenómeno nacional uniforme. Un revisor puede señalar que los resultados son representativos del litoral peruano, no del país.
