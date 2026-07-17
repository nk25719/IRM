from __future__ import annotations

from collections import Counter, defaultdict
import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.database import get_sqlite_database_path
from scripts.master_data_utils import ARTIFACT_DIR, CONFIG_DIR, normalize_value, trimmed_value, write_csv

MANUFACTURER_COLUMNS = {
    "equipment": ["manufacturer"],
    "equipment_models": ["manufacturer"],
    "equipment_assets": ["company", "supplier"],
    "inventory_items": ["manufacturer"],
    "inventory": ["manufacturer", "brand"],
    "service_reports": ["supplier"],
}


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not exists:
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def collect_values() -> tuple[list[dict], list[dict]]:
    conn = sqlite3.connect(get_sqlite_database_path())
    conn.row_factory = sqlite3.Row
    raw_rows = []
    model_profile = []
    try:
        for table, wanted_columns in MANUFACTURER_COLUMNS.items():
            cols = existing_columns(conn, table)
            for column in wanted_columns:
                if column not in cols:
                    continue
                query = f'SELECT "{column}" AS value, COUNT(*) AS occurrence_count FROM "{table}" WHERE "{column}" IS NOT NULL AND TRIM(CAST("{column}" AS TEXT)) != "" GROUP BY TRIM(CAST("{column}" AS TEXT))'
                for row in conn.execute(query):
                    raw = row["value"]
                    raw_rows.append(
                        {
                            "source_table": table,
                            "source_column": column,
                            "raw_value": raw,
                            "trimmed_value": trimmed_value(raw),
                            "normalized_value": normalize_value(raw),
                            "occurrence_count": row["occurrence_count"],
                            "equipment_count": "",
                            "model_count": "",
                            "proposed_canonical_manufacturer": trimmed_value(raw),
                            "match_method": "exact-normalized-candidate",
                            "confidence": 50,
                            "requires_review": "true",
                            "review_notes": "candidate only; legal/brand relationships require approval",
                        }
                    )
        if {"manufacturer", "model"}.issubset(existing_columns(conn, "equipment_models")):
            for row in conn.execute(
                'SELECT manufacturer, COUNT(*) AS model_count FROM equipment_models WHERE manufacturer IS NOT NULL AND TRIM(manufacturer) != "" GROUP BY manufacturer'
            ):
                model_profile.append(
                    {
                        "manufacturer": row["manufacturer"],
                        "normalized_manufacturer": normalize_value(row["manufacturer"]),
                        "model_count": row["model_count"],
                    }
                )
    finally:
        conn.close()

    counts = Counter((row["normalized_value"], row["trimmed_value"]) for row in raw_rows)
    for row in raw_rows:
        row["model_count"] = next((p["model_count"] for p in model_profile if p["normalized_manufacturer"] == row["normalized_value"]), "")
    duplicate_candidates = [
        {
            "normalized_value": normalized,
            "candidate_values": " | ".join(sorted({value for n, value in counts if n == normalized})),
            "source_count": sum(1 for row in raw_rows if row["normalized_value"] == normalized),
            "requires_review": "true",
        }
        for normalized in sorted({row["normalized_value"] for row in raw_rows})
        if sum(1 for row in raw_rows if row["normalized_value"] == normalized) > 1
    ]
    unmatched = [row for row in raw_rows if row["requires_review"] == "true"]
    return raw_rows, duplicate_candidates, unmatched, model_profile


def main() -> None:
    values, duplicates, unmatched, model_profile = collect_values()
    fieldnames = [
        "source_table",
        "source_column",
        "raw_value",
        "trimmed_value",
        "normalized_value",
        "occurrence_count",
        "equipment_count",
        "model_count",
        "proposed_canonical_manufacturer",
        "match_method",
        "confidence",
        "requires_review",
        "review_notes",
    ]
    write_csv(ARTIFACT_DIR / "manufacturer-values.csv", fieldnames, values)
    write_csv(ARTIFACT_DIR / "manufacturer-duplicate-candidates.csv", ["normalized_value", "candidate_values", "source_count", "requires_review"], duplicates)
    write_csv(ARTIFACT_DIR / "manufacturer-unmatched-values.csv", fieldnames, unmatched)
    write_csv(ARTIFACT_DIR / "equipment-model-manufacturer-profile.csv", ["manufacturer", "normalized_manufacturer", "model_count"], model_profile)
    write_csv(
        CONFIG_DIR / "manufacturer_mapping.csv",
        [
            "approved",
            "raw_value",
            "normalized_value",
            "canonical_code",
            "canonical_name",
            "match_action",
            "alias_source",
            "confidence",
            "review_notes",
        ],
        [
            {
                "approved": "false",
                "raw_value": row["raw_value"],
                "normalized_value": row["normalized_value"],
                "canonical_code": "",
                "canonical_name": row["proposed_canonical_manufacturer"],
                "match_action": "review",
                "alias_source": f'{row["source_table"]}.{row["source_column"]}',
                "confidence": row["confidence"],
                "review_notes": row["review_notes"],
            }
            for row in values
        ],
    )
    print(f"wrote {len(values)} manufacturer value rows")


if __name__ == "__main__":
    main()
