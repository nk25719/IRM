from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date
from typing import Any

import pandas as pd

EVENT_KEYS = ("serviceContract", "engineer", "callreassons", "title", "start", "end")
CONTRACT_RE = re.compile(r"\bSC/[A-Za-z0-9][A-Za-z0-9/_-]*")


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "nat", "0000-00-00"}:
        return None
    parsed = pd.to_datetime(text[:19], errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _balanced_candidates(html: str) -> list[str]:
    candidates = []
    for match in re.finditer(r"[\[{]", html):
        start = match.start()
        opener = html[start]
        closer = "]" if opener == "[" else "}"
        depth = 0
        in_string = None
        escaped = False
        for idx in range(start, min(len(html), start + 250000)):
            char = html[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == in_string:
                    in_string = None
                continue
            if char in {"'", '"'}:
                in_string = char
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    chunk = html[start : idx + 1]
                    if any(key in chunk for key in EVENT_KEYS):
                        candidates.append(chunk)
                    break
    return candidates


def _to_python(value: str) -> Any:
    cleaned = re.sub(r"/\*.*?\*/", "", value, flags=re.S)
    cleaned = re.sub(r"//.*?$", "", cleaned, flags=re.M)
    cleaned = re.sub(r"([{,]\s*)([A-Za-z_$][A-Za-z0-9_$-]*)(\s*:)", r'\1"\2"\3', cleaned)
    cleaned = re.sub(r",(\s*[\]}])", r"\1", cleaned)
    cleaned = re.sub(r"\btrue\b", "True", cleaned)
    cleaned = re.sub(r"\bfalse\b", "False", cleaned)
    cleaned = re.sub(r"\bnull\b", "None", cleaned)
    return ast.literal_eval(cleaned)


def _walk_events(value: Any) -> list[dict]:
    events = []
    if isinstance(value, list):
        for item in value:
            events.extend(_walk_events(item))
    elif isinstance(value, dict):
        keys = set(value)
        if keys.intersection(EVENT_KEYS) and ("start" in keys or "title" in keys or "serviceContract" in keys):
            events.append(value)
        for item in value.values():
            if isinstance(item, (list, dict)):
                events.extend(_walk_events(item))
    return events


def _first_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("name", "title", "label", "value", "text"):
            if value.get(key):
                return str(value[key]).strip()
        return None
    text = str(value).strip()
    return text or None


def _event_type(payload: dict) -> str:
    text = json.dumps(payload, default=str)
    if "serviceContract" in payload or "serviceContract" in text:
        return "service_contract"
    if "pm" in text.lower() or "preventive" in text.lower():
        return "pm_task"
    return "calendar_event"


def _contract_reference(payload: dict) -> str | None:
    match = CONTRACT_RE.search(json.dumps(payload, default=str))
    return match.group(0) if match else None


def _normalize_event(payload: dict) -> dict:
    title = _first_text(payload.get("title") or payload.get("name"))
    service_contract = payload.get("serviceContract")
    return {
        "source": "mdmanser_calendar",
        "source_event_key": _stable_hash(payload),
        "event_type": _event_type(payload),
        "title": title,
        "engineer_name": _first_text(payload.get("engineer")),
        "call_reasons": _first_text(payload.get("callreassons") or payload.get("call_reasons")),
        "contract_reference": _contract_reference(payload),
        "client_name": _first_text(payload.get("institution") or payload.get("client") or payload.get("hospital")),
        "equipment_name": _first_text(payload.get("equipment") or payload.get("model") or payload.get("device")),
        "start_date": _parse_date(payload.get("start") or payload.get("date")),
        "end_date": _parse_date(payload.get("end")),
        "raw_payload": json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False),
    }


def parse_mdmanser_calendar_html(html: str) -> list[dict]:
    events_by_key = {}
    for chunk in _balanced_candidates(html):
        try:
            parsed = _to_python(chunk)
        except (SyntaxError, ValueError):
            continue
        for payload in _walk_events(parsed):
            event = _normalize_event(payload)
            events_by_key[event["source_event_key"]] = event
    return list(events_by_key.values())
