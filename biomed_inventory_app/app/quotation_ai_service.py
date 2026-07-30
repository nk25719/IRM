from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Protocol

from pydantic import BaseModel, Field


VALIDATION_OK = "ok"
VALIDATION_WARNING = "warning"
VALIDATION_MISMATCH = "mismatch"
VALIDATION_MISSING_INFO = "missing_info"


AI_QUOTATION_ENABLED = os.getenv("AI_QUOTATION_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
AI_QUOTATION_PROVIDER = os.getenv("AI_QUOTATION_PROVIDER", "disabled")
AI_QUOTATION_MODEL = os.getenv("AI_QUOTATION_MODEL", "")
AI_QUOTATION_BASE_URL = os.getenv("AI_QUOTATION_BASE_URL", "")
AI_QUOTATION_TIMEOUT_SECONDS = int(os.getenv("AI_QUOTATION_TIMEOUT_SECONDS", "30"))
AI_QUOTATION_MAX_INPUT_LENGTH = int(os.getenv("AI_QUOTATION_MAX_INPUT_LENGTH", "12000"))
AI_QUOTATION_STORE_PROMPTS = os.getenv("AI_QUOTATION_STORE_PROMPTS", "false").lower() in {"1", "true", "yes", "on"}
AI_QUOTATION_STORE_RESPONSES = os.getenv("AI_QUOTATION_STORE_RESPONSES", "false").lower() in {"1", "true", "yes", "on"}


class QuotationContext(BaseModel):
    client_id: int | None = None
    client_name: str | None = None
    site_id: int | None = None
    site_name: str | None = None
    contact_id: int | None = None
    contact_name: str | None = None
    equipment_id: int | None = None
    equipment_name: str | None = None
    service_case_id: int | None = None
    service_report_number: str | None = None
    preferred_currency: str | None = "USD"
    quotation_template: str | None = "CMM Financial Offer"


class ExtractedClient(BaseModel):
    id: int | None = None
    name: str | None = None
    site_id: int | None = None
    site_name: str | None = None
    contact_id: int | None = None
    contact_name: str | None = None


class ExtractedEquipment(BaseModel):
    equipment_id: int | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    asset_number: str | None = None


class ExtractedReferences(BaseModel):
    service_case_id: int | None = None
    service_report_number: str | None = None
    customer_reference: str | None = None


class ExtractedTechnicalSummary(BaseModel):
    reported_issue: str | None = None
    inspection_findings: str | None = None
    diagnosis: str | None = None
    troubleshooting_performed: list[str] = Field(default_factory=list)
    recommended_action: str | None = None


class ExtractedItem(BaseModel):
    item_type: str = "part"
    description: str | None = None
    part_number: str | None = None
    quantity: float | None = 1
    unit: str | None = "piece"
    unit_price: float | None = None
    currency: str | None = None
    discount_percent: float = 0
    tax_percent: float | None = None
    warranty: str | None = None
    source_text: str | None = None
    confidence: str | None = Field(default="Low", pattern="^(High|Medium|Low)$")


class ExtractedLabour(BaseModel):
    description: str | None = None
    hours: float | None = None
    hourly_rate: float | None = None
    technician_count: int = 1
    currency: str | None = None
    source_text: str | None = None
    confidence: str | None = Field(default="Low", pattern="^(High|Medium|Low)$")


class ExtractedCommercialTerms(BaseModel):
    currency: str | None = None
    quotation_validity_days: int | None = None
    delivery_time: str | None = None
    payment_terms: str | None = None
    warranty: str | None = None
    tax_included: bool | None = None
    shipping_included: bool | None = None


class QuotationExtractionResult(BaseModel):
    client: ExtractedClient = Field(default_factory=ExtractedClient)
    equipment: ExtractedEquipment = Field(default_factory=ExtractedEquipment)
    references: ExtractedReferences = Field(default_factory=ExtractedReferences)
    technical_summary: ExtractedTechnicalSummary = Field(default_factory=ExtractedTechnicalSummary)
    items: list[ExtractedItem] = Field(default_factory=list)
    labour: list[ExtractedLabour] = Field(default_factory=list)
    commercial_terms: ExtractedCommercialTerms = Field(default_factory=ExtractedCommercialTerms)
    notes: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QuotationExtractionProvider(Protocol):
    async def extract_quotation(self, text: str, context: QuotationContext) -> QuotationExtractionResult:
        ...


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


@dataclass
class RuleBasedQuotationExtractionProvider:
    def extract_quotation_sync(self, text: str, context: QuotationContext) -> QuotationExtractionResult:
        source = text[:AI_QUOTATION_MAX_INPUT_LENGTH]
        lower = source.casefold()
        currency = _extract_currency(source) or context.preferred_currency or "USD"
        part_number = _first_match(r"(?:part\s*(?:number|no\.?|#)|p/?n)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9_.\-/]+)", source)
        quantity = _number_before(r"(?:flow\s+sensor|sensor|part|piece|pcs|units?)", source) or 1
        unit_price = _price_near(source, ["sensor", "part", part_number or ""])
        labour_hours = _first_float(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s*(?:labou?r|work|service)?", lower)
        labour_rate = _price_near(source, ["labour", "labor", "hour"])
        warranty = _first_match(r"warranty\s+([A-Za-z0-9 ]{3,40})", source)
        diagnosis = _sentence_with(lower, source, ["defective", "faulty", "failed", "broken"])
        issue = _sentence_with(lower, source, ["problem", "issue", "fault", "not working"]) or source[:240]
        action = _sentence_with(lower, source, ["replace", "replacement", "corrective", "repair"]) or ("Replace defective part" if part_number or "sensor" in lower else None)
        items = []
        if part_number or "sensor" in lower or unit_price is not None:
            items.append(ExtractedItem(
                item_type="part",
                description="Flow sensor" if "flow sensor" in lower else None,
                part_number=part_number,
                quantity=quantity,
                unit_price=unit_price,
                currency=currency if unit_price is not None else None,
                warranty=warranty,
                source_text=_sentence_with(lower, source, [part_number or "sensor", "price"]) or source[:240],
                confidence="High" if part_number and unit_price is not None else "Medium",
            ))
        labour = []
        if labour_hours is not None or labour_rate is not None or "labour" in lower or "labor" in lower:
            labour.append(ExtractedLabour(
                description="Corrective maintenance labour",
                hours=labour_hours,
                hourly_rate=labour_rate,
                currency=currency if labour_rate is not None else None,
                source_text=_sentence_with(lower, source, ["labour", "labor", "hour"]) or source[:240],
                confidence="High" if labour_hours is not None and labour_rate is not None else "Medium",
            ))
        missing = []
        if not context.client_id and not context.client_name:
            missing.append("Client must be confirmed from IRM records.")
        if not part_number and items:
            missing.append("Part number is missing or unclear.")
        if any(item.unit_price is None for item in items):
            missing.append("Unit price for one or more parts is missing.")
        if any(row.hours is None for row in labour):
            missing.append("Labour hours are missing.")
        if any(row.hourly_rate is None for row in labour):
            missing.append("Labour rate is missing.")
        if not currency:
            missing.append("Currency was not specified.")
        if not warranty:
            missing.append("Warranty period was not found.")
        result = QuotationExtractionResult(
            client=ExtractedClient(id=context.client_id, name=context.client_name, site_id=context.site_id, site_name=context.site_name, contact_id=context.contact_id, contact_name=context.contact_name),
            equipment=ExtractedEquipment(equipment_id=context.equipment_id, model=context.equipment_name),
            references=ExtractedReferences(service_case_id=context.service_case_id, service_report_number=context.service_report_number),
            technical_summary=ExtractedTechnicalSummary(reported_issue=issue, inspection_findings=diagnosis, diagnosis=diagnosis, troubleshooting_performed=[], recommended_action=action),
            items=items,
            labour=labour,
            commercial_terms=ExtractedCommercialTerms(currency=currency, warranty=warranty),
            missing_information=missing,
            warnings=["AI extraction creates an editable draft only; review every commercial and technical value before approval."],
        )
        return QuotationExtractionResult.model_validate(result.model_dump())

    async def extract_quotation(self, text: str, context: QuotationContext) -> QuotationExtractionResult:
        return self.extract_quotation_sync(text, context)


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.I)
    return match.group(1).strip(" .,:;") if match else None


def _first_float(pattern: str, text: str) -> float | None:
    value = _first_match(pattern, text)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _extract_currency(text: str) -> str | None:
    lower = text.casefold()
    if "usd" in lower or "dollar" in lower:
        return "USD"
    if "eur" in lower or "euro" in lower:
        return "EUR"
    if "lbp" in lower:
        return "LBP"
    return None


def _number_before(pattern: str, text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s+" + pattern, text, re.I)
    return float(match.group(1)) if match else None


def _price_near(text: str, terms: list[str]) -> float | None:
    for term in [t for t in terms if t]:
        safe = re.escape(term)
        patterns = [
            rf"{safe}.{{0,50}}?(?:price|cost|rate)\s*(?:is|=|:)?\s*(\d+(?:\.\d+)?)\s*(?:usd|dollars?|\$)?",
            rf"{safe}.{{0,50}}?(\d+(?:\.\d+)?)\s*(?:usd|dollars?|\$)",
            rf"(\d+(?:\.\d+)?)\s*(?:usd|dollars?|\$).{{0,50}}?{safe}",
        ]
        for pattern in patterns:
            value = _first_float(pattern, text)
            if value is not None:
                return value
    return None


def _sentence_with(lower: str, original: str, terms: list[str]) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", original)
    for sentence in sentences:
        folded = sentence.casefold()
        if any(term and term.casefold() in folded for term in terms):
            return sentence.strip()
    return None
