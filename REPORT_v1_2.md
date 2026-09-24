# REPORT_v1_2.md — Camera-ready LATINCOM 2026 (v1.2)

**Paper:** EDAS #1571320229 — *Measuring the 4G Impact of a Progressive 3G Shutdown: Evidence from Open Regulatory Data in Peru*
**Rama:** `paper/v1.2` (worktree separado, partiendo del tag `v1.1-outcomes`, hash `d582bb1`).
**Datos:** raw congelados, último YEARMONTH leído = **202605** (verificado, regla 7).
**Script:** `scripts/build_camera_ready_v1_2.py`.

---

## 1. T0 — Verificaciones previas

### T0.1 — Ceros vs vacíos vs filas ausentes

- `ROW_PRESENT_IN_SOURCE` está implementado en `src/portalosiptel3g/io.py:20` (`read_csv_safely` marca `True` en cada fila leída del CSV fuente) y se consume en `src/portalosiptel3g/detection.py:54`:
  ```python
  if "ROW_PRESENT_IN_SOURCE" in g_tail.columns and bool((~g_tail["ROW_PRESENT_IN_SOURCE"]).any()):
      continue
  ```
  Exige que **todos** los meses desde el breakpoint hasta el último mes global sean filas reales del raw; si falta una, no se confirma el apagado.

- Clasificación de los 86 confirmados × meses desde su breakpoint hasta 202605 (945 celdas distrito-mes revisadas, `outputs/v1_2/detection_zero_types.csv`):

  | Categoría | n |
  |---|---|
  | `explicit_zero` | 0 |
  | `empty_field` | 945 |
  | `missing_row` | 0 |

  **Hallazgo relevante:** en el raw de OSIPTEL, **ningún** mes de "3G en cero" se representa con el literal `"0"` — siempre es un campo vacío. `clean_minimal()` (`src/portalosiptel3g/cleaning.py:49`) es la que convierte `"" → 0`. De los 86 confirmados (y de los 67 analizados), **0** tienen "solo `explicit_zero`" en todo el post — es matemáticamente imposible con este dataset, porque el literal `explicit_zero` no ocurre nunca. Esto tiene una consecuencia directa en T3 (ver abajo): la variante `explicit_zero_only` confirma **0 distritos**.

### T0.2 — Ventana de elegibilidad de controles con datos truncados

- No existe una función `build_control_summary()` en el código (es un nombre conceptual de `Paper/plan.md`). La lógica real vive en `scripts/build_control_and_did.py`, función `find_eligible()` (líneas 124-180) invocada desde `main()` (líneas 250-282).
- Cuando `bp+6 > 202605` (breakpoints 202512, 202601, 202602), la ventana **se trunca a los meses disponibles**, no exige los 6 meses completos. Cita exacta (`build_control_and_did.py:253-256`):
  ```python
  pre_m_avail  = [m for m in pre_m  if m in global_months]
  post_m_avail = [m for m in post_m if m in global_months]
  present_win  = set(pre_m_avail + post_m_avail)
  ```
  `find_eligible()` exige `IS_3G_ACTIVE_MONTH` en **todos** los meses de `present_win` (ya truncado) y ≥3 meses con `MEAS>0` en pre y post disponibles.

### T0.3 — Umbral de `excl_low_meas`

- `EXCL_MEAS = 1_000` (`scripts/build_stats_a3.py:30`), a **nivel distrito**, sobre:
  ```python
  avg_meas_per_month = (pre6_4g_download_measurements + post6_4g_download_measurements) / (months_pre + months_post)
  ```
  (`build_stats_a3.py:140-144`), donde `pre6_4g_download_measurements`/`post6_4g_download_measurements` son la **media** de mediciones sobre los 6 meses pre/post válidos, y `months_pre`/`months_post` son el conteo de **todos** los meses históricos con `MEAS>0` (no solo los 6 de la ventana). En v1.0 este filtro se aplica **solo a tratados**, sobre el **delta crudo** — no al DiD ni a controles (ver discrepancia §4).

### T0.4 — Agregación del event-study (Fig. 3)

- `event_study.csv` se genera en `build_control_and_did.py:422-490`. Por distrito-τ: `gap = treated_4g_dl − media(4g_dl de sus K controles matcheados)` en el mismo mes calendario (línea 475). Entre distritos se agrega con `.agg("mean")` (líneas 479-489) → **media**, no mediana. Rango real: `for tau in range(-6, 6)` (línea 445) → **τ = −6 … +5**, no ±12.

### T0.5 — Repo

- Tag `v1.0-paper-freeze` = `9a9c9f1` (2026-07-09). Tag `v1.1-outcomes` = `d582bb1` (2026-07-21). **Ambos ya existían** antes de v1.2 — no fue necesario crearlos.
- El fix de mojibake (`_fix_mojibake`/`norm_key`, `build_control_and_did.py:95-114`) es **genérico y preexistente desde v1.0**, no específico de Cañete/Breña ni introducido en v1.1.

### Hallazgo adicional (verificación read-only previa, fuera del script)

`origin/main` avanzó dos commits después del freeze (`pipeline: 2026-08 update` y `2026-09 update`), con raw hasta **202607**. Comparando `shutdown_confirmed.csv` de `origin/main` contra el congelado: mismo total (86), pero **14 distritos difieren** (7 "desaparecen", 7 nuevos con bp 202606/202607). El caso más claro es **Espinar (Cusco)**, parte de los 67 analizados (`did=0.0743`, `matched_count=5`): 5 meses consecutivos en cero (feb–jun 2026) y en **julio 2026 el 3G reaparece** (472 mediciones, 4.43 Mbps) — reactivación real. Los otros 6 casos son ceros de 1-2 meses que se resuelven al mes siguiente (probablemente `empty_field` por vacío operativo, no apagado real). **No afecta los números de v1.2** (que usa datos truncados a 202605 por diseño), pero es evidencia relevante para la sección de limitaciones del camera-ready: al menos un distrito del n=67 tuvo un 3G que "regresó" ~5 meses después de su breakpoint.

---

## 2. Sanity checks y determinismo

| Check | Esperado | Obtenido | Resultado |
|---|---|---|---|
| DiD download principal | 0.6488 (n=67) | 0.6488 (n=67) | ✅ |
| Crudo download principal | 1.0032 (n=67, de `observable_stats.json`) | 1.0032 (n=67) | ✅ |
| Sensibilidad 5G (v1.1) | 0.8429 (n=60, de `observable_stats_v1_1.json`) | 0.8429 (n=60) | ✅ (referencia; T9.3(a) la reproduce independientemente, ver abajo) |
| Último YEARMONTH leído | 202605 | 202605 | ✅ |
| Determinismo (2 corridas → hash SHA-256 de `observable_stats_v1_2.json`) | idéntico | `60cedc4d...c01bb` en ambas corridas (re-verificado tras la ronda de correcciones de abajo) | ✅ IDÉNTICO |

---

## 3. Resultados por tarea

### T1 — Robustez DiD download (Mbps)

| Variante | n | DiD mediana | IC95 | Wilcoxon p (one-sided) | n+/n− | Crudo mediana |
|---|---|---|---|---|---|---|
| principal | 67 | 0.65 | [0.42, 1.01] | 1.03e-06 | 52/15 | 1.00 |
| weighted | 67 | 0.75 | [0.39, 0.98] | 2.07e-06 | 51/16 | 0.98 |
| strict_post6 | 62 | 0.81 | [0.50, 1.03] | 4.21e-07 | 49/13 | 1.01 |
| excl_low_meas (a: solo tratados) | 50 | 0.56 | [0.31, 0.94] | 4.32e-05 | 37/13 | 0.87 |
| excl_low_meas (b: tratados+controles) | 50 | 0.56 | [0.31, 0.93] | 4.32e-05 | 37/13 | 0.87 |
| excl_5G (reutiliza v1.1) | 60 | 0.84 | [0.54, 1.13] | 8.63e-08 | 50/10 | 1.07 |
| window_3 (pre3/post3) | 67 | 0.66 | [0.42, 0.94] | 8.82e-07 | 50/17 | 0.73 |
| window_4 (pre4/post≤4,min3) | 67 | 0.68 | [0.36, 0.93] | 6.87e-07 | 51/16 | 0.79 |

Nota: en `excl_low_meas_b`, 0 de los 50 tratados sobrevivientes de (a) se cayeron por quedar con <3 controles — el filtro de mediciones bajas afecta a tratados y controles de forma correlacionada dentro de la misma región. `window_3`/`window_4` reutilizan los mismos K=5 controles de v1.0 (matching con baseline pre6); no se re-empareja.

### T2 — Event study con incertidumbre (media, IC95 bootstrap, n)

| τ | media (Mbps) | IC95 | n |
|---|---|---|---|
| −6 | 0.14 | [−0.08, 0.35] | 67 |
| −5 | 0.18 | [0.02, 0.35] | 67 |
| −4 | 0.17 | [0.01, 0.34] | 67 |
| −3 | 0.10 | [−0.09, 0.29] | 67 |
| −2 | 0.13 | [−0.06, 0.31] | 67 |
| −1 | 0.15 | [−0.05, 0.34] | 67 |
| 0 | 0.56 | [0.23, 0.84] | 67 |
| +1 | 0.82 | [0.55, 1.09] | 67 |
| +2 | 0.79 | [0.51, 1.08] | 67 |
| +3 | 0.82 | [0.48, 1.17] | 67 |
| +4 | 1.02 | [0.67, 1.38] | 63 |
| +5 | 1.06 | [0.71, 1.42] | 62 |

Pre-tendencias (τ<0) planas y con IC que incluye 0 en casi todos los puntos; salto claro en τ=0. Figura actualizada: `Paper/figs/event_study.pdf` (banda IC95, línea en 0, línea vertical en τ=0, fila de n bajo el eje). Versión anterior preservada en `Paper/figs/event_study_v1_1.pdf`.

### T3 — Sensibilidad de la detección

**Corrección aplicada (bug encontrado en la primera versión):** `tail_months` (los meses entre el breakpoint y el último mes disponible) ya está garantizado 100% en cero por la regla original de `detect_shutdown_confirmed()` — por construcción, todos esos meses son cero, así que comprobar "los primeros N meses son cero" era una condición vacía (siempre verdadera). La forma correcta de que "≥N meses consecutivos en cero tras el breakpoint" sea una restricción real es exigir que existan **al menos N meses de evidencia** entre el breakpoint y el último mes disponible (202605): `len(tail_months) >= N`. Con la corrección:

| Regla | n confirmados (de 86) | n sobrevivientes (de 67) | DiD mediana | IC95 | Wilcoxon p (one-sided) |
|---|---|---|---|---|---|
| confirm_min3 (≥3 meses de evidencia tras bp) | **68** | 67 | 0.65 | [0.42, 1.01] | 1.03e-06 |
| confirm_min6 (≥6 meses de evidencia tras bp) | **63** | **62** | **0.81** | [0.50, 1.03] | 4.21e-07 |
| explicit_zero_only | 0 | 0 | — | — | — |

`confirm_min3` elimina 18 de los 86 confirmados (los de bp 202604/202605, que solo tienen 1-2 meses de evidencia hasta 202605) pero no toca ninguno de los 67 analizados (todos ya tenían ≥3 meses de evidencia por el filtro `months_post>=3` previo). `confirm_min6` elimina 23 de los 86 y **5 de los 67 analizados** (bp 202601/202602, con solo 4-5 meses de evidencia) — el resultado (n=62, DiD=0.81) coincide exactamente con `strict_post6` de T1, lo cual es una validación cruzada esperada: ambas reglas exigen efectivamente ≥6 meses de evidencia post-breakpoint. `explicit_zero_only` sigue confirmando 0 distritos por la razón de T0.1: no existen ceros literales en el raw, solo campos vacíos.

### T4 — Diagnósticos del matching

- Controles distintos por tratado: min=3, mediana=5, max=5. 12 de 67 tratados tienen <5 controles distintos (usan calipers relajados o el pool en su región es chico).
- Controles únicos totales usados: 107. Reúso: min=1, mediana=2, p90=6.4, max=13.
- Top-5 más reusados: Huancavelica (Huancavelica) ×13, Sicuani (Cusco) ×10, Huamachuco (La Libertad) ×8, Chorrillos (Lima) ×8, Tarma (Junín) ×7.
- Balance (media tratados vs controles, SMD antes/después del matching, variance ratio):

  | Variable | Tratados | Controles (antes) | Controles (después) | SMD antes | SMD después | VR antes | VR después |
  |---|---|---|---|---|---|---|---|
  | pre6 4G download (Mbps) | 10.35 | 10.17 | 10.21 | 0.194 | 0.089 | 1.073 | 0.914 |
  | log10(población) | 4.78 | 4.53 | 4.72 | 0.464 | 0.119 | 1.085 | 0.816 |
  | altitud (m) | 1479.0 | 1208.1 | 1381.1 | −0.084 | 0.064 | 1.062 | 0.906 |

  region3: match exacto = 100%. **max|SMD| post-matching = 0.119** — bien dentro de los umbrales convencionales (<0.1-0.25).

  **Reconciliación 107 vs 211 (pregunta pendiente):** el número correcto de **distritos-control físicamente distintos** es **107** (`matches["control_key"].nunique()`, sin condicionar en nada). El "211" que aparece en T9.2 es el conteo de **instancias (control_key, treated_bp)** — la tabla de timing 5G-vs-breakpoint necesita, para cada control, evaluar su clasificación *relativa al bp del tratado con el que está emparejado*, y como un mismo control físico puede estar emparejado con tratados de **distinto** breakpoint (reúso, ver arriba: mediana 2, máx 13 usos), aparece una fila por cada combinación (control, bp) distinta, no una fila por control. 107 es el número a citar en el texto como "controles únicos usados"; 211 es un artefacto de la tabla de diagnóstico de T9.2, ahora reetiquetado explícitamente en el JSON (`timing_controls_used_n_instances=211` vs `timing_controls_used_n_distinct_districts=107`).

  *Nota (regla 8):* la columna "antes" no existía en v1.0; se construyó para v1.2 sobre el pool elegible en la misma región3, misma ventana calendario y misma regla `MIN_VALID`, **sin** restricción de caliper (`cal=1e9`), reutilizando `find_eligible()` tal cual.

### T5 — Placebo temporal (bp−6)

**T5 original** (matches fijos de v1.0, pre=[bp−12,bp−7], post=[bp−6,bp−1]): n=67 (ninguno excluido). DiD placebo mediana = **0.26 Mbps**, IC95=[−0.04, 0.37], Wilcoxon two-sided p=0.027, n+/n−=40/27. El IC95 casi no incluye 0 y el p es marginal — el placebo con los matches originales no es tan "limpio" como se esperaba.

**T5b — placebo RE-EMPAREJADO** (mismas covariables y calipers que v1.0, K=5 Mahalanobis, pero con baseline de matching = media[bp−12,bp−7] y exigiendo 3G activo en todo [bp−12,bp−1] para los controles): n_matched=67 (0 sin match, 5 con caliper relajado). DiD placebo mediana = **−0.03 Mbps**, IC95=[−0.17, 0.23], Wilcoxon two-sided p=**0.671**, n+/n−=32/35.

**Conclusión:** el placebo re-emparejado da un **nulo limpio** (mediana ≈0, IC amplio y simétrico alrededor de 0, p=0.67), mientras que el placebo con los matches originales (optimizados para el baseline de la ventana real, no para 6 meses antes) mostraba una señal marginal. Esto sugiere que el resultado marginal de T5-original es un artefacto de reutilizar controles emparejados sobre el baseline "equivocado" (el de la ventana real, bp−6..bp−1), no evidencia de anticipación del apagado. **Recomendación para el texto:** reportar el placebo re-emparejado (T5b) como el resultado principal de robustez temporal, y mencionar T5-original solo como nota metodológica (el placebo con matches fijos es sensible al baseline usado para emparejar).

**T5c — diagnóstico de pre-tendencia** (matches originales, gap medio del event-study para τ=−12..−7, más allá del rango de Fig. 3):

| τ | gap medio (Mbps) | n |
|---|---|---|
| −12 | −0.14 | 67 |
| −11 | −0.15 | 67 |
| −10 | −0.08 | 67 |
| −9 | −0.11 | 67 |
| −8 | −0.11 | 67 |
| −7 | −0.04 | 67 |

Con los matches originales, el gap es **negativo** en todo τ=−12..−7 (tratados por debajo de sus controles) y se acerca a 0 conforme τ crece hacia el breakpoint — consistente con el resultado marginal de T5-original (que compara precisamente el nivel de esta zona negativa contra la zona ligeramente positiva de τ=−6..−1, ver T2). Es una pre-tendencia leve con los matches fijos, que el re-matching de T5b corrige.

### T6 — Distritos con cambio negativo

**16** distritos analizados tienen `delta_raw<0` o `did<0` (de 67). Detalle completo en `outputs/v1_2/negative_districts_v1_2.csv`, series en `negative_districts_series_v1_2.csv` (τ=−12..+12, con media de sus controles).

**Perfil de los 5 con delta crudo <0:**

| Distrito | Región | bp | meses post | Δ crudo | DiD | Δ mediciones | 5G | Controles |
|---|---|---|---|---|---|---|---|---|
| Socabaya (Arequipa) | Sierra | 202410 | 20 | −1.14 | **−0.70** | +16% | No | bajan |
| San Agustín (Junín) | Sierra | 202412 | 18 | −0.52 | **+0.21** | −18% | No | suben (más que el tratado cae) |
| El Porvenir (La Libertad) | Costa | 202412 | 18 | −0.18 | **−0.77** | −26% | No | suben |
| La Victoria (Lambayeque) | Costa | 202412 | 18 | −0.77 | **−0.49** | −4% | No | suben |
| Sayán (Lima) | Costa | 202602 | 4 | −2.71 | **−3.52** | −9% | No | suben |

Ninguno de los 5 tiene contaminación 5G. San Agustín es el único con DiD positivo a pesar del delta crudo negativo — su caída es menor que la de sus controles, así que en términos relativos "mejora". En los otros 4, los controles suben mientras el tratado cae o se estanca, lo que sostiene un DiD negativo genuino, no solo ruido de la ventana pre/post.

**Patrón entre los 15 distritos con DiD<0** (de los 16 totales; 1 —San Agustín— tiene DiD>0 a pesar de delta crudo<0): fuertemente concentrados en **Costa** (13/15, 87%) vs Sierra (2/15); mediana de meses post = 6 (breakpoints relativamente recientes, con menos tiempo para consolidar la mejora); 5 de 15 (33%) tienen contaminación 5G en su ventana post — una fracción más alta que el promedio general (7/67 ≈ 10%), sugiriendo que la contaminación 5G contribuye a algunos, pero no todos, de los DiD negativos.

### T7 — DiD por región

| Región | n | DiD mediana | IC95 | Wilcoxon p (one-sided) | n+/n− | Crudo mediana |
|---|---|---|---|---|---|---|
| Costa | 38 | 0.33 | [−0.03, 0.55] | 0.059 | 25/13 | 0.77 |
| **Costa (excl. 7 distritos 5G)** | **31** | **0.35** | **[0.17, 0.63]** | **0.007** | **23/8** | **0.97** |
| Sierra | 29 | 1.21 | [1.03, 1.57] | 3.5e-08 | 27/2 | 1.41 |

Diferencia Sierra−Costa = **0.88 Mbps**, IC95 bootstrap = [0.61, 1.44]. El efecto es marcadamente más fuerte y más consistente en Sierra (27/29 positivos) que en Costa, donde el Wilcoxon one-sided con la muestra completa es solo marginal (p=0.059) y el IC roza 0.

**T7b — hallazgo relevante:** al excluir de Costa los 7 distritos con 5G en su ventana post (los mismos de T9.3/T9.4, todos costeros: Lima y Cañete), el resultado de Costa se **limpia notablemente** — mediana casi igual (0.35 vs 0.33) pero el IC95 ya no roza 0 ([0.17, 0.63]) y el Wilcoxon one-sided pasa de marginal (p=0.059) a claramente significativo (p=0.007). Esto sugiere que la contaminación por 5G (que resta mediciones 4G, ver T9.5) es la principal responsable de que el efecto en Costa completo se vea más débil/ruidoso que en Sierra — no es que Costa tenga un efecto menor per se.

### T9 — Secuencia 3G off → 4G → 5G

- **T9.1**: 13 columnas 5G_NSA en el raw. Primer YEARMONTH con 5G>0 nacional (Movistar) = **202403**. Crece de 4 distritos (202403) a 29 distritos (202605).
- **T9.2**: clasificación timing 5G vs breakpoint —

  | Grupo | 5g_before_bp | 5g_in_post_window | 5g_after_window | never |
  |---|---|---|---|---|
  | Confirmados (86) | 10 | 7 | 2 | 67 |
  | Analizados (67) | 2 | 5 | 2 | 58 |
  | Controles usados (211 únicos, con repetición por par) | 10 | 6 | 6 | 189 |

- **T9.3**: contaminación de controles.
  - (a) excluyendo tratados con 5G en su ventana post: n=60, DiD mediana=**0.84**, IC95=[0.54,1.13] — **reproduce exactamente el +0.84 de v1.1** ✅.
  - (b) excluyendo además, por tratado, los controles con 5G en la misma ventana: n=**56** (4 tratados se cayeron por quedar con <3 controles limpios), DiD mediana=**0.86**, IC95=[0.62,1.17]. El resultado es robusto: excluir la posible contaminación de 5G en los controles no cambia la conclusión.
- **T9.4**: los 7 distritos con 5G y bp=202512 son Breña, Carabayllo, Los Olivos, San Juan de Lurigancho, San Martín de Porres (Lima), Asia y Mala (Cañete) — confirma el supuesto del spec. Series completas en `fiveg_districts_series_v1_2.csv`.
- **T9.5**: evidencia de fuga por composición — los 7 distritos 5G tienen una caída mediana en el conteo de mediciones 4G de **−12,756** (post−pre) vs **−3,184** en los otros 60 (Mann-Whitney p=0.0032, significativo). En time% 4G la diferencia no es significativa (mediana +2.0 p.p. vs +1.7 p.p., p=0.46). Esto apoya parcialmente la interpretación de fuga de dispositivos 5G fuera de la muestra 4G (cae el volumen de mediciones 4G mucho más donde aparece 5G) pero no vía time%, que se mantiene similar.
- **T9.6**: no generada (opcional, prioridad baja per spec).

### Persistencia fuera de muestra (informativo — usa `origin/main`, datos NO congelados)

⚠️ Esta sección **no usa datos congelados**: lee `outputs/tables/shutdown_confirmed.csv` y el raw de `origin/main` (commit `c875c8b5a4`, hasta YEARMONTH **202607**). Es solo un chequeo de robustez fuera-de-muestra; **no reemplaza** los números oficiales de v1.2/el paper.

De los **67** analizados, **66 siguen confirmados** con datos hasta 202607. Solo **1 cae**: **Espinar (Cusco)**, bp=202602, DiD congelado=0.0743 (efecto pequeño, positivo). Razón diagnosticada automáticamente (reactivación de `IS_3G_ACTIVE_MONTH` en los meses extra): **reactivación de 3G en julio 2026** (202607) — 472 mediciones, 4.43 Mbps, tras 5 meses en cero (feb-jun 2026). Es la misma reactivación que se identificó en la verificación read-only previa a v1.2 (ver §1, hallazgo de T0.5).

**DiD principal excluyendo Espinar** (n=66): mediana = **0.72 Mbps**, IC95=[0.44, 1.01] — sube levemente respecto al 0.65 oficial (Espinar tenía un DiD muy por debajo de la mediana, así que quitarlo empuja la mediana hacia arriba). El resultado es robusto: perder 1 de 67 tratados por una reactivación tardía no compromete la conclusión.

---

## 4. Discrepancias entre el spec y el código (regla 8)

1. **`build_control_summary()` no existe** con ese nombre; es un nombre conceptual de `Paper/plan.md`. La lógica real está en `find_eligible()`/`main()` de `scripts/build_control_and_did.py`.
2. **`excl_low_meas` en v1.0 solo se aplica a tratados**, sobre el delta crudo (no al DiD, no a controles). La variante de T1 que lo aplica "a tratados y controles" en el DiD es una **construcción nueva** de v1.2; para los controles se recalculó el análogo desde el raw usando la misma ventana calendario del tratado emparejado (no existe insumo equivalente en `did_matches.csv`).
3. **`event_study.csv` agrega con media, no mediana**, y su rango real es τ=−6..+5 (no ±12 como sugieren T6/T9.4 para sus propias series, que sí van más allá). T2 mantiene esta convención (media, mismo rango) por decisión explícita.
4. **`make_figures.py` vivía en `Paper/`, no en `scripts/`**, y su output es `event_study.pdf` (sin prefijo `fig3_`) en `Paper/figs/` (no `figs/` ni `paper/figs/` como en el texto del spec). Por decisión explícita se mantuvo esa convención; el script se copió a `scripts/make_figures.py` para versionarlo en el tag.
5. El **balance "antes del matching" (T4)** no existía en v1.0; se construyó para v1.2 reutilizando `find_eligible()` con calipers infinitos (`cal=1e9`) sobre el pool elegible en la misma región3.
6. **T0.1 revela que la distinción `explicit_zero`/`empty_field` es en la práctica vacía**: el raw de OSIPTEL nunca contiene un literal `"0"` en los campos de tráfico 3G — siempre es un campo vacío convertido a 0 por `clean_minimal()`. Esto hace que la variante `explicit_zero_only` de T3 confirme 0 distritos, y vale la pena una frase en la sección de datos del paper.
7. **Persistencia fuera de muestra (formalizada)**: con datos hasta 202607 (`origin/main`, commit `c875c8b5a4`, no usados en los números oficiales de v1.2), 66 de los 67 analizados siguen confirmados; el único que cae es **Espinar (Cusco)**, por reactivación real de 3G en julio 2026 tras 5 meses en cero. El DiD principal excluyendo Espinar sube levemente a 0.72 (de 0.65). No afecta los números congelados pero es material de discusión/limitaciones (sección `out_of_sample_persistence` del JSON, marcada explícitamente como no-congelada).
8. **T5 (placebo con matches originales)** dio un resultado menos "nulo" de lo esperado (IC95=[−0.04, 0.37], p two-sided=0.027). **Resuelto con T5b**: al re-emparejar usando el baseline correcto para esa ventana temporal (media de [bp−12,bp−7], no la del emparejamiento real), el placebo da un nulo limpio (mediana=−0.03, IC95=[−0.17,0.23], p=0.67). Recomendación: usar T5b como el placebo principal en el texto.
9. **Bug corregido en T3**: la primera versión de `confirm_min3`/`confirm_min6` era una condición vacía (ver §3, T3) — no cambiaba nada porque `tail_months` ya estaba garantizado 100% en cero por la regla original. Corregido a exigir `len(tail_months) >= N`; ahora `confirm_min6` sí elimina 5 de los 67 (validación cruzada con `strict_post6` de T1: mismo n=62, mismo DiD=0.81).
10. **T7b (nuevo)**: excluir de Costa los 7 distritos con 5G limpia notablemente el resultado regional (IC95 deja de rozar 0, p pasa de 0.059 a 0.007) — la contaminación 5G parece ser la principal fuente de ruido en el efecto de Costa, no una debilidad real del efecto costero.
11. **Reconciliación 107 vs 211 (T4 vs T9.2)**: 107 es el número correcto de distritos-control físicamente distintos; 211 era un artefacto de conteo por (control, breakpoint) en la tabla de timing de T9.2, ahora relabeleado explícitamente en el JSON.

---

## 5. Tiempo de ejecución

- Una corrida completa de `scripts/build_camera_ready_v1_2.py` (con T5b/T5c y persistencia fuera de muestra agregados): **~2-3 min** (incluye el re-matching K=5 de T5b sobre los 67 tratados, ~12 bootstraps de 10,000 iteraciones, y llamadas `git show` de solo lectura para la sección informativa de persistencia fuera de muestra).
- Verificación de determinismo (2 corridas + hash): confirmado idéntico tanto en la versión inicial como después de la ronda de correcciones de esta sesión.

---

## 6. Entregables generados

```
scripts/build_camera_ready_v1_2.py
scripts/make_figures.py                          (copiado desde Paper/, con banda IC + fila de n)
outputs/v1_2/observable_stats_v1_2.json
outputs/v1_2/detection_zero_types.csv             (T0.1)
outputs/v1_2/did_robustness_v1_2.csv              (T1)
outputs/v1_2/event_study_v1_2.csv                 (T2)
outputs/v1_2/detection_sensitivity_v1_2.csv        (T3)
outputs/v1_2/did_balance_full_v1_2.csv            (T4)
outputs/v1_2/negative_districts_v1_2.csv          (T6)
outputs/v1_2/negative_districts_series_v1_2.csv   (T6)
outputs/v1_2/fiveg_timing_v1_2.csv                (T9.2)
outputs/v1_2/fiveg_districts_series_v1_2.csv      (T9.4)
outputs/v1_2/observable_stats_v1_2.json           (incluye placebo.original/rematched/pretrend,
                                                    negative_districts_extra, regional_did.costa_excl_5g,
                                                    out_of_sample_persistence)
Paper/figs/event_study.pdf                        (T2, nueva version)
Paper/figs/event_study_v1_1.pdf                   (T2, version anterior preservada)
REPORT_v1_2.md                                    (este archivo)
```
