from pathlib import Path
import pandas as pd

KEYS = [
    "ADM_LEVEL_1_NAME",
    "ADM_LEVEL_2_NAME",
    "ADM_LEVEL_3_NAME",
    "NETWORK_CARRIER",
]


def write_outputs(
    df_all: pd.DataFrame,
    core_df: pd.DataFrame,
    out_dir: Path,
    write_filtered: bool = False,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs = {}

    # Output core
    core_path = out_dir / "shutdown_confirmed.csv"
    core_df.to_csv(core_path, index=False, encoding="utf-8")
    outputs["core"] = core_path

    # Dataset derivado (opcional)
    if write_filtered:
        filtered = df_all.merge(core_df[KEYS], on=KEYS, how="inner")
        filtered_path = out_dir / "dataset_2023_2025_shutdown_districts.csv"
        filtered.to_csv(filtered_path, index=False, encoding="utf-8")
        outputs["filtered"] = filtered_path

    return outputs
