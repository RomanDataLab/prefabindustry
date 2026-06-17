#!/usr/bin/env python3
# Check company webpages and fill missing legal names using OpenAI

import sys
import os
import csv
import json
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Fix Windows encoding issues
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Add parent directory to path to import apiManager
sys.path.insert(0, str(Path(__file__).parent.parent))
from configix.apiManager import get_ai_provider  # type: ignore

try:
    from openai import OpenAI
except ImportError:
    print("Error: openai package not installed. Run: pip install openai")
    sys.exit(1)

# Initialize OpenAI with API key from configix
openai_config = get_ai_provider("ai_openai")
openai_client = OpenAI(api_key=openai_config["api_key"])


def call_openai(messages: List[Dict], max_retries: int = 3) -> str:
    """Call OpenAI API with basic retry logic."""
    for i in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3,
                max_tokens=1500,
            )
            return response.choices[0].message.content or ""
        except Exception as error:  # noqa: BLE001
            error_str = str(error).lower()
            # Simple backoff on rate limits
            if any(
                kw in error_str
                for kw in [
                    "rate limit",
                    "quota",
                    "429",
                    "resource_exhausted",
                    "too many requests",
                ]
            ):
                backoff_time = min(60 * (i + 1), 180)
                print(f"  ⚠️  Rate limit hit. Waiting {backoff_time}s...")
                if i < max_retries - 1:
                    time.sleep(backoff_time)
                    continue
            print(f"  ⚠️  Attempt {i + 1}/{max_retries} failed: {error}")
            if i == max_retries - 1:
                raise
            time.sleep(2 * (i + 1))
    return ""


def normalize_missing(value: Optional[str]) -> str:
    """Normalize missing-like values to empty string."""
    if value is None:
        return ""
    v = str(value).strip()
    if v in ("", "NaN", "nan", "null", "None"):
        return ""
    return v


def build_webpage_check_prompt(
    brand: str, legal_name: str, webpage: str, country: str, address: str
) -> str:
    """Create prompt asking AI whether to keep/remove row based on webpage."""
    today = time.strftime("%Y-%m-%d")
    context_lines = [
        f"Brand: {brand or 'Unknown'}",
        f"Legal name: {legal_name or 'Unknown'}",
        f"Country: {country or 'Unknown'}",
        f"Address: {address or 'Unknown'}",
        f"Webpage: {webpage or 'Unknown'}",
    ]
    context_str = "\n".join(context_lines)

    return f"""You are validating the official website of a prefab / modular housing company.

Date today: {today}

Company context:
{context_str}

Evaluate this specific URL ONLY as of today:
- Is the site reachable and actually live (not obviously dead, domain for sale, or parked)?
- Is it in practice the official site of this company (not clearly unrelated spam or a totally different business)?
- When you open the homepage in a modern browser, does it show a critical browser security warning on start (e.g. malware/phishing warning, dangerous site, or blocking TLS/HTTPS certificate issue that normal users will see)?

Return ONLY a compact JSON object in this exact format:
{{
  "decision": "keep" | "remove",
  "reason": "very short explanation (max 140 chars)"
}}

Rules:
- Use "remove" if the site is dead, clearly not the company's real site, obviously parked/for-sale, or has strong browser security warnings on start.
- Use "keep" if the site is working and looks like a normal plausible company homepage (even if simple).
- If you are unsure, default to "keep"."""


def should_keep_row(row: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """Decide whether to keep this row based on the webpage using AI.

    Returns (keep_row, reason_if_removed).
    """
    webpage_raw = row.get("webpage", "")
    webpage = normalize_missing(webpage_raw)

    # If there is no webpage at all, we cannot check it – keep the row.
    if not webpage:
        return True, None

    brand = normalize_missing(row.get("brand"))
    legal_name = normalize_missing(row.get("head_office_legal_name"))
    country = normalize_missing(row.get("country"))
    address = normalize_missing(row.get("address"))

    prompt = build_webpage_check_prompt(brand, legal_name, webpage, country, address)

    try:
        response = call_openai([{"role": "user", "content": prompt}])
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ Error calling OpenAI for webpage check: {e}")
        # On failure, be conservative and keep the row
        return True, None

    if not response:
        return True, None

    # Try to extract a JSON object from the response
    json_match = re.search(r"\{[\s\S]*\}", response)
    if not json_match:
        return True, None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return True, None

    decision = str(data.get("decision", "keep")).strip().lower()
    reason = data.get("reason") or None

    if decision == "remove":
        return False, reason

    return True, None


def build_legal_name_prompt(
    brand: str, webpage: str, address: str, country: str
) -> str:
    """Create prompt asking AI to find official legal name."""
    today = time.strftime("%Y-%m-%d")
    return f"""You are researching the official registered legal name of a prefab / modular housing company.

Use any information you can infer from the website and public business registries as of {today}.

Company details:
- Brand (trading) name: {brand or 'Unknown'}
- Website: {webpage or 'Unknown'}
- Address: {address or 'Unknown'}
- Country: {country or 'Unknown'}

Return ONLY valid JSON in this exact format:
{{
  "head_office_legal_name": "full official registered company name, including legal form like Ltd, LLC, GmbH, SA, Oy, AB, etc, or null if truly unknown"
}}

Rules:
- Only provide a value if you are reasonably confident it is the exact registered legal name.
- If you cannot find a reliable legal name, use null.
- Do not return any explanation, only the JSON object."""


def fill_missing_legal_name(row: Dict[str, str]) -> Dict[str, str]:
    """If head_office_legal_name is missing/NaN, use AI to fill it based on webpage."""
    current_legal = normalize_missing(row.get("head_office_legal_name"))
    if current_legal:
        return row

    webpage = normalize_missing(row.get("webpage"))
    if not webpage:
        # No webpage to research – nothing to do
        return row

    brand = normalize_missing(row.get("brand"))
    address = normalize_missing(row.get("address"))
    country = normalize_missing(row.get("country"))

    prompt = build_legal_name_prompt(brand, webpage, address, country)

    try:
        response = call_openai([{"role": "user", "content": prompt}])
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ Error calling OpenAI for legal name: {e}")
        return row

    if not response:
        return row

    json_match = re.search(r"\{[\s\S]*\}", response)
    if not json_match:
        return row

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return row

    legal_name = data.get("head_office_legal_name")
    if legal_name is None:
        return row

    legal_name_str = str(legal_name).strip()
    if not legal_name_str or legal_name_str.lower() in {"null", "nan", "none"}:
        return row

    new_row = row.copy()
    new_row["head_office_legal_name"] = legal_name_str
    return new_row


def main() -> None:
    """Main entry: filter rows by webpage and fill missing legal names."""
    root_dir = Path(__file__).parent.parent
    input_csv_path = root_dir / "maps" / "public" / "prefabworldfin.csv"

    if not input_csv_path.exists():
        print(f"❌ Input file not found: {input_csv_path}")
        sys.exit(1)

    output_csv_path = input_csv_path.with_name(
        f"{input_csv_path.stem}_reducedby_1.csv"
    )

    print("🚀 Starting webpage check and legal-name enrichment using OpenAI...\n")
    print(f"Input CSV:  {input_csv_path}")
    print(f"Output CSV: {output_csv_path}\n")

    # Read entire CSV
    with open(input_csv_path, "r", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    print(f"📖 Loaded {len(rows)} rows\n")

    kept_rows: List[Dict[str, str]] = []
    removed_count = 0
    updated_legal_names = 0

    for idx, row in enumerate(rows, start=1):
        company_id = row.get("id", str(idx))
        brand = normalize_missing(row.get("brand"))
        webpage = normalize_missing(row.get("webpage"))

        print(f"[{idx}/{len(rows)}] Checking ID {company_id} – {brand or 'Unknown'}")

        keep, reason = should_keep_row(row)
        if not keep:
            removed_count += 1
            print(
                f"  ❌ Removing row due to webpage issue"
                f"{f' ({reason})' if reason else ''}"
            )
            # Small delay to avoid hammering the API too fast
            time.sleep(0.5)
            continue

        print("  ✅ Webpage accepted (row kept)")

        # If legal name is missing/NaN, try to fill it using AI
        before_legal = normalize_missing(row.get("head_office_legal_name"))
        if not before_legal:
            print("  🔍 head_office_legal_name is missing – researching...")
            new_row = fill_missing_legal_name(row)
            after_legal = normalize_missing(new_row.get("head_office_legal_name"))
            if after_legal and after_legal != before_legal:
                updated_legal_names += 1
                print(f"  ✅ Filled legal name: {after_legal}")
            else:
                print("  ⚠️ Could not confidently find legal name")
            row = new_row
            # Slight delay for rate limiting
            time.sleep(1.0)

        kept_rows.append(row)

        # Progress checkpoint every 25 rows
        if idx % 25 == 0:
            print(f"\n💾 Progress: {idx}/{len(rows)} rows processed\n")

    # Write result CSV
    print(
        f"\n💾 Writing {len(kept_rows)} kept rows to: {output_csv_path.name}"
    )
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in kept_rows:
            writer.writerow(row)

    print("\n📊 Summary:")
    print(f"  Total rows input:      {len(rows)}")
    print(f"  Rows removed:          {removed_count}")
    print(f"  Rows kept:             {len(kept_rows)}")
    print(f"  Legal names updated:   {updated_legal_names}")
    print("\n🎉 Done!")


if __name__ == "__main__":
    main()

