En tu README.md, solo necesitas 4 secciones:

1 Qué hace el proyecto

Detecta distritos donde el 3G de MOVISTAR está efectivamente apagado usando KPIs OSIPTEL (2023–2025).

2 Regla técnica (resumen)

3G activo = DL > 0 y mediciones > 0

Breakpoint = primer mes donde DL=0 y mediciones=0

Confirmado si:

se mantiene hasta último mes

≥ 3 meses ACTIVE previos

3 Comandos
portalosiptel3g detect --data-dir data\raw --carrier MOVISTAR --write-filtered
portalosiptel3g inspect --data-dir data\raw --carrier MOVISTAR --adm3 "Jose Luis Bustamante Y Rivero"

4 Outputs

shutdown_confirmed.csv → verdad lógica

dataset_2023_2025_shutdown_districts.csv → dataset de análisis

portalosiptel3g.log → trazabilidad técnica