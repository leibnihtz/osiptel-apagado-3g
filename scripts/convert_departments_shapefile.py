"""
Convierte Limite_Departamental shapefile a GeoJSON simplificado para Observable.
"""
import json
import geopandas as gpd
from pathlib import Path

SHP = Path("Limite_Departamental/Departamental INEI 2023 geogpsperu SuyoPomalia.shp")
OUT = Path("outputs/observable/data/observable_departments_inei_2023_simplified.geojson")
TOLERANCE = 0.01  # grados (~1km) — suficiente para nivel departamental

gdf = gpd.read_file(SHP)

# Asegurar WGS84
if gdf.crs.to_epsg() != 4326:
    gdf = gdf.to_crs(epsg=4326)

# Reparar geometrías inválidas y simplificar
gdf["geometry"] = gdf["geometry"].buffer(0)
gdf["geometry"] = gdf["geometry"].simplify(TOLERANCE, preserve_topology=True)

# Mantener solo columnas necesarias
gdf = gdf[["CCDD", "DEPARTAMEN", "geometry"]]

OUT.parent.mkdir(parents=True, exist_ok=True)
gdf.to_file(OUT, driver="GeoJSON")

size_kb = OUT.stat().st_size / 1024
print(f"Generado: {OUT}")
print(f"Features: {len(gdf)}")
print(f"Tamaño: {size_kb:.1f} KB")
