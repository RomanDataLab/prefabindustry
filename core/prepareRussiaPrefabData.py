#!/usr/bin/env python3
"""
Prepare Russia prefab company data for integration into prefabworld.

Steps:
- Load research_output/russia_prefab_core_21.csv
- Drop duplicate companies by (brand, webpage)
- Remove any companies that already exist in maps/public/prefabworldfin.csv
  (matched by brand + normalized webpage)
- Add missing columns so the output schema matches maps/public/prefabworldfin.csv
  (including enrichment columns like type, viz, plans), using the same
  content logic used there for Russia rows:
    - country      -> "Russia"
    - country_code -> "RUS"
    - region       -> empty (can be filled later)
    - latitude     -> empty (can be geocoded later)
    - longitude    -> empty (can be geocoded later)
"""

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
    # Remove trailing slashes and whitespace
    url = url.rstrip("/")
    return url


def load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV file with UTF-8 encoding and basic error handling."""
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    return pd.read_csv(path, encoding="utf-8")


def build_russia_candidates(
    russia_core_path: Path,
    prefabworldfin_path: Path,
) -> pd.DataFrame:
    """
    Create a cleaned Russia dataframe:
    - unique by (brand, webpage)
    - excluding rows already present in prefabworldfin.csv by (brand, normalized webpage)
    - with columns aligned to prefabworldfin.csv (including enrichment columns)
    """
    print(f"Loading Russia core data from: {russia_core_path}")
    df_ru = load_csv(russia_core_path)

    print(f"Loading existing prefabworld final data from: {prefabworldfin_path}")
    df_worldfin = load_csv(prefabworldfin_path)

    required_cols = {"brand", "webpage"}
    missing_ru = required_cols - set(df_ru.columns)
    missing_world = required_cols - set(df_worldfin.columns)
    if missing_ru:
        raise ValueError(f"Russia core CSV is missing required columns: {missing_ru}")
    if missing_world:
        raise ValueError(f"prefabworldfin CSV is missing required columns: {missing_world}")

    # 1) Reduce Russia rows to unique (brand, webpage)
    before_dedup = len(df_ru)
    df_ru = df_ru.copy()
    df_ru["webpage_norm"] = df_ru["webpage"].apply(normalize_url)
    df_ru_unique = df_ru.drop_duplicates(subset=["brand", "webpage_norm"])
    after_dedup = len(df_ru_unique)
    print(f"Deduplicated Russia rows by (brand, webpage): {before_dedup} -> {after_dedup}")

    # 2) Build key set from prefabworldfin to exclude already present companies
    df_worldfin = df_worldfin.copy()
    df_worldfin["webpage_norm"] = df_worldfin["webpage"].apply(normalize_url)

    # Perform an anti-join on (brand, webpage_norm)
    merged = df_ru_unique.merge(
        df_worldfin[["brand", "webpage_norm"]],
        on=["brand", "webpage_norm"],
        how="left",
        indicator=True,
        suffixes=("", "_world"),
    )

    candidates = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
    candidates = candidates.drop(columns=["webpage_norm"])

    print(
        "Filtered out companies already in prefabworldfin: "
        f"{after_dedup} -> {len(candidates)} remaining candidates"
    )

    # 3) Align columns to prefabworldfin.csv schema (dynamic, including enrichment columns)
    prefab_schema = list(df_worldfin.columns)

    # Ensure all schema columns exist
    candidates = candidates.copy()

    # Fill obvious Russia-specific data with same logic as existing prefabworld Russia rows
    if "country" not in candidates.columns:
        candidates["country"] = "Russia"
    else:
        candidates["country"] = candidates["country"].fillna("Russia")

    if "country_code" not in candidates.columns:
        candidates["country_code"] = "RUS"
    else:
        candidates["country_code"] = candidates["country_code"].fillna("RUS")

    if "region" not in candidates.columns:
        candidates["region"] = pd.NA

    if "latitude" not in candidates.columns:
        candidates["latitude"] = pd.NA
    if "longitude" not in candidates.columns:
        candidates["longitude"] = pd.NA

    # Create any other missing columns as empty
    for col in prefab_schema:
        if col not in candidates.columns:
            candidates[col] = pd.NA

    # Reorder columns to match prefabworldfin.csv
    candidates = candidates[prefab_schema]

    return candidates


def main():
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent

    research_dir = root_dir / "research_output"
    maps_public_dir = root_dir / "maps" / "public"

    russia_core_path = research_dir / "russia_prefab_core_21.csv"
    prefabworldfin_path = maps_public_dir / "prefabworldfin.csv"
    output_path = research_dir / "russia_prefab_core_21_cleaned.csv"

    print("Preparing Russia prefab data...")
    candidates = build_russia_candidates(russia_core_path, prefabworldfin_path)

    print(f"Saving cleaned Russia candidates to: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_path, index=False, encoding="utf-8")

    print("\nDone.")
    print(f"   Total output rows: {len(candidates)}")
    print(f"   Output schema columns: {len(candidates.columns)} (matches prefabworldfin.csv)")


if __name__ == "__main__":
    # Allow running as a module or script
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

