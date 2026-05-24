from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.mdmanser_client import MDManserClient, mdmanser_base_url, mdmanser_session_configured  # noqa: E402
from app.mdmanser_parser import parse_mdmanser_calendar_html  # noqa: E402


def main():
    print(f"MDMANSER_BASE_URL configured: {bool(os.getenv('MDMANSER_BASE_URL'))}")
    print(f"MDMANSER_BASE_URL effective: {mdmanser_base_url()}")
    print(f"MDMANSER_PHPSESSID configured: {mdmanser_session_configured()}")
    try:
        client = MDManserClient()
        html = client.get_calendar_html(5, 2026)
    except Exception as exc:
        print(f"read_error: {exc}")
        raise SystemExit(1)
    lowered = html.lower()
    print(f"status_code: {client.last_status_code}")
    print(f"html_length: {len(html)}")
    print(f"contains_serviceContract: {'serviceContract' in html}")
    print(f"contains_engineer: {'engineer' in lowered}")
    print(f"contains_callreassons: {'callreassons' in lowered}")
    events = parse_mdmanser_calendar_html(html)
    print(f"parsed_event_count: {len(events)}")


if __name__ == "__main__":
    main()
