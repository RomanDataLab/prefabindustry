#!/usr/bin/env python3
"""
Merge cleaned Russia prefab data into maps/public/prefabworldfin.csv.

Steps:
- Load maps/public/prefabworldfin.csv (current global dataset)
- Load research_output/russia_prefab_core_21_cleaned.csv (Russia candidates,
  already deduped and schema-aligned to prefabworldfin)
- Defensively drop any Russia rows whose (brand, webpage) already exist
  in prefabworldfin (using normalized URLs)
- Assign new unique IDs for the Russia rows (continuing from max existing id)
- Append Russia rows to prefabworldfin and overwrite prefabworldfin.csv
  (a backup copy is written before overwrite)
"""

import shutil
import sys
from pathlib import Path

import pandas as pd


def normalize_url(url: str) -> str:
    """Normalize webpage URLs for more robust matching."""
    if not isinstance(url, str):
        return url
    url = url.strip()
    if not url:
        return url
    # Remove trailing slash
    url = url.rstrip("/")
    return url


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    return pd.read_csv(path, encoding="utf-8")


def main():
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    maps_public_dir = root_dir / "maps" / "public"
    research_dir = root_dir / "research_output"

    prefabworldfin_path = maps_public_dir / "prefabworldfin.csv"
    russia_clean_path = research_dir / "russia_prefab_core_21_cleaned.csv"

    print(f"Loading prefabworldfin from: {prefabworldfin_path}")
    df_world = load_csv(prefabworldfin_path)

    print(f"Loading cleaned Russia data from: {russia_clean_path}")
    df_ru = load_csv(russia_clean_path)

    # Ensure we have brand + webpage columns
    for df_name, df in [("prefabworldfin", df_world), ("russia_cleaned", df_ru)]:
        missing = {"brand", "webpage"} - set(df.columns)
        if missing:
            raise ValueError(f"{df_name} is missing required columns: {missing}")

    # Align schemas: use prefabworldfin columns as the master schema
    master_cols = list(df_world.columns)

    # Add any missing columns in Russia df
    for col in master_cols:
        if col not in df_ru.columns:
            df_ru[col] = pd.NA

    # Also make sure any extra columns in Russia df are dropped
    df_ru = df_ru[master_cols]

    # Defensive duplicate protection: filter out Russia rows already present by (brand, normalized webpage)
    df_world = df_world.copy()
    df_ru = df_ru.copy()

    df_world["webpage_norm"] = df_world["webpage"].apply(normalize_url)
    df_ru["webpage_norm"] = df_ru["webpage"].apply(normalize_url)

    existing_keys = set(
        zip(df_world["brand"].astype(str), df_world["webpage_norm"].astype(str))
    )

    def is_new_row(row) -> bool:
        key = (str(row["brand"]), str(row["webpage_norm"]))
        return key not in existing_keys

    before_filter = len(df_ru)
    df_ru_new = df_ru[df_ru.apply(is_new_row, axis=1)].drop(columns=["webpage_norm"])
    df_world = df_world.drop(columns=["webpage_norm"])

    print(
        "Russia candidates filtered by (brand, webpage): "
        f"{before_filter} -> {len(df_ru_new)} rows to append"
    )

    if len(df_ru_new) == 0:
        print("No new Russia rows to merge. Exiting.")
        return

    # Assign new unique IDs for Russia rows
    if "id" not in df_world.columns:
        raise ValueError("prefabworldfin.csv has no 'id' column.")

    id_series = pd.to_numeric(df_world["id"], errors="coerce")
    if id_series.notna().any():
        max_id = int(id_series.max())
    else:
        max_id = 0

    new_ids = range(max_id + 1, max_id + 1 + len(df_ru_new))
    df_ru_new = df_ru_new.copy()
    df_ru_new["id"] = list(new_ids)

    print(f"Assigned IDs to Russia rows from {max_id + 1} to {max_id + len(df_ru_new)}")

    # Concatenate and write back, keeping a backup
    df_merged = pd.concat([df_world, df_ru_new], ignore_index=True)

    backup_path = prefabworldfin_path.with_name("prefabworldfin_before_russia.csv")
    print(f"Creating backup of prefabworldfin at: {backup_path}")
    shutil.copy2(prefabworldfin_path, backup_path)

    print(f"Writing merged data to: {prefabworldfin_path}")
    df_merged.to_csv(prefabworldfin_path, index=False, encoding="utf-8")

    print("\nMerge complete.")
    print(f"   Original rows: {len(df_world)}")
    print(f"   Russia rows added: {len(df_ru_new)}")
    print(f"   New total rows: {len(df_merged)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

