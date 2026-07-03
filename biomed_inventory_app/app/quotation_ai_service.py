from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Protocol


VALIDATION_OK = "ok"
VALIDATION_WARNING = "warning"
VALIDATION_MISMATCH = "mismatch"
VALIDATION_MISSING_INFO = "missing_info"


class QuotationAIProvider(Protocol):
    def validate_item(self, item: dict[str, Any], inventory_rows: list[dict[str, Any]]) -> dict[str, Any]:
        ...


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())


def normalized_description(item: dict[str, Any]) -> str:
    code = str(item.get("item_code") or item.get("manufacturer_part_number") or "").strip()
    desc = str(item.get("description") or "").strip()
    if code and desc and code.lower() not in desc.lower():
        return f"{code} - {desc}"
    return desc or code


@dataclass
class RuleBasedQuotationAIProvider:
    min_confidence: float = 0.58

    def validate_item(self, item: dict[str, Any], inventory_rows: list[dict[str, Any]]) -> dict[str, Any]:
        missing = []
        if not str(item.get("description") or "").strip():
            missing.append("description")
        if float(item.get("quantity") or 0) <= 0:
            missing.append("quantity")
        if item.get("unit_price") is None:
            missing.append("unit_price")

        best = self._best_inventory_match(item, inventory_rows)
        notes: list[str] = []
        status = VALIDATION_OK
        confidence = best["confidence"] if best else 0.0

        if missing:
            status = VALIDATION_MISSING_INFO
            notes.append(f"Missing required field(s): {', '.join(missing)}.")
        elif best and confidence >= self.min_confidence:
            item_code = normalize_text(item.get("item_code") or item.get("manufacturer_part_number"))
            matched_code = normalize_text(best["row"].get("pn") or best["row"].get("inventory_id"))
            if item_code and matched_code and item_code not in matched_code and matched_code not in item_code and confidence < 0.82:
                status = VALIDATION_MISMATCH
                notes.append(f"Possible code mismatch with inventory item {best['row'].get('pn') or best['row'].get('inventory_id')}.")
            else:
                notes.append(f"Possible inventory match: {best['row'].get('pn') or best['row'].get('inventory_id')}.")
        else:
            status = VALIDATION_WARNING if not missing else status
            notes.append("No confident inventory match found.")

        normalized = normalized_description(item)
        if normalized and normalized != str(item.get("description") or "").strip():
            notes.append("Normalized description suggestion is available; original text was not changed.")

        return {
            "inventory_item_id": best["row"].get("id") if best and confidence >= self.min_confidence else None,
            "ai_normalized_description": normalized or None,
            "ai_match_confidence": round(confidence, 3),
            "ai_validation_status": status,
            "ai_validation_notes": " ".join(notes).strip(),
            "match": best["row"] if best and confidence >= self.min_confidence else None,
        }

    def _best_inventory_match(self, item: dict[str, Any], inventory_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        item_code = normalize_text(item.get("item_code") or item.get("manufacturer_part_number"))
        item_desc = normalize_text(item.get("description"))
        needle = " ".join(part for part in [item_code, item_desc] if part)
        if not needle:
            return None

        best: dict[str, Any] | None = None
        for row in inventory_rows:
            row_code = normalize_text(row.get("pn") or row.get("inventory_id"))
            row_desc = normalize_text(row.get("description"))
            row_text = " ".join(part for part in [row_code, row_desc, normalize_text(row.get("manufacturer"))] if part)
            code_score = 1.0 if item_code and row_code and (item_code == row_code or item_code in row_code or row_code in item_code) else 0.0
            text_score = SequenceMatcher(None, needle, row_text).ratio() if row_text else 0.0
            desc_score = SequenceMatcher(None, item_desc, row_desc).ratio() if item_desc and row_desc else 0.0
            confidence = max(code_score, (text_score * 0.65) + (desc_score * 0.35))
            if best is None or confidence > best["confidence"]:
                best = {"row": row, "confidence": confidence}
        return best


class QuotationAIService:
    def __init__(self, provider: QuotationAIProvider | None = None):
        self.provider = provider or RuleBasedQuotationAIProvider()

    def validate_items(self, items: list[dict[str, Any]], inventory_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for item in items:
            result = self.provider.validate_item(item, inventory_rows)
            results.append({**item, **result})
        return results
