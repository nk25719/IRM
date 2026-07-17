from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.database import get_sqlite_database_path
from scripts.master_data_utils import ARTIFACT_DIR, CONFIG_DIR, normalize_value, trimmed_value, write_csv

CATEGORY_COLUMNS = {
    "equipment": ["category", "equipment_type", "device_type", "description", "name"],
    "equipment_models": ["model"],
    "equipment_assets": ["product_type", "model"],
    "inventory_items": ["category", "description"],
    "inventory": ["item_category", "device_family", "description"],
    "procurement_requests": ["category"],
    "sales_requests": ["category"],
    "sales_request_items": ["category"],
}

TAXONOMY_HINTS = {
    "ventilator": ("RESP", "Respiratory", "Critical Care Ventilator"),
    "spirometer": ("RESP", "Respiratory", "Spirometer"),
    "monitor": ("PMON", "Patient Monitoring", "Multiparameter Monitor"),
    "ecg": ("PMON", "Patient Monitoring", "ECG"),
    "ultrasound": ("IMG", "Diagnostic Imaging", "Ultrasound"),
    "x-ray": ("IMG", "Diagnostic Imaging", "X-Ray"),
    "infusion": ("INF", "Infusion", "Infusion Pump"),
    "syringe": ("INF", "Infusion", "Syringe Pump"),
    "spare_parts": ("PARTS", "Parts and Accessories", ""),
    "accessories": ("PARTS", "Parts and Accessories", ""),
}


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not exists:
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def propose(raw: str) -> tuple[str, str, str, int, str]:
    normalized = normalize_value(raw)
    for token, (code, parent, child) in TAXONOMY_HINTS.items():
        if token in normalized:
            category = child or parent
            return category, parent if child else "", code, 65, "taxonomy keyword candidate; requires review"
    return trimmed_value(raw), "", "", 30, "unmatched candidate; requires review"


def main() -> None:
    conn = sqlite3.connect(get_sqlite_database_path())
    conn.row_factory = sqlite3.Row
    rows = []
    try:
        for table, wanted in CATEGORY_COLUMNS.items():
            cols = existing_columns(conn, table)
            for column in wanted:
                if column not in cols:
                    continue
                for row in conn.execute(
                    f'SELECT "{column}" AS value, COUNT(*) AS count FROM "{table}" WHERE "{column}" IS NOT NULL AND TRIM(CAST("{column}" AS TEXT)) != "" GROUP BY TRIM(CAST("{column}" AS TEXT))'
                ):
                    raw = row["value"]
                    category, parent, code, confidence, notes = propose(str(raw))
                    rows.append(
                        {
                            "raw_value": raw,
                            "normalized_value": normalize_value(raw),
                            "source": f"{table}.{column}",
                            "count": row["count"],
                            "proposed_canonical_category": category,
                            "proposed_parent_category": parent,
                            "confidence": confidence,
                            "requires_review": "true",
                            "notes": notes,
                        }
                    )
    finally:
        conn.close()
    fields = ["raw_value", "normalized_value", "source", "count", "proposed_canonical_category", "proposed_parent_category", "confidence", "requires_review", "notes"]
    write_csv(ARTIFACT_DIR / "equipment-category-values.csv", fields, rows)
    write_csv(ARTIFACT_DIR / "equipment-category-candidates.csv", fields, rows)
    write_csv(ARTIFACT_DIR / "equipment-category-unmatched.csv", fields, [row for row in rows if int(row["confidence"]) < 60])
    write_csv(
        CONFIG_DIR / "equipment_category_mapping.csv",
        [
            "approved",
            "raw_value",
            "normalized_value",
            "canonical_code",
            "canonical_name",
            "parent_code",
            "parent_name",
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
                "canonical_code": row["proposed_canonical_category"].upper().replace(" ", "_")[:40],
                "canonical_name": row["proposed_canonical_category"],
                "parent_code": "",
                "parent_name": row["proposed_parent_category"],
                "match_action": "review",
                "alias_source": row["source"],
                "confidence": row["confidence"],
                "review_notes": row["notes"],
            }
            for row in rows
        ],
    )
    print(f"wrote {len(rows)} category value rows")


if __name__ == "__main__":
    main()
