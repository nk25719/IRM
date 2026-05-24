from __future__ import annotations

import os
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_MDMANSER_BASE_URL = "https://cmm.mdmanser.com"
MDMANSER_COOKIE_DOMAIN = "cmm.mdmanser.com"


class MDManserConfigurationError(RuntimeError):
    pass


class MDManserAuthenticationError(RuntimeError):
    pass


class MDManserRequestError(RuntimeError):
    pass


def mdmanser_base_url() -> str:
    return os.getenv("MDMANSER_BASE_URL", DEFAULT_MDMANSER_BASE_URL).strip().rstrip("/")


def mdmanser_session_configured() -> bool:
    return bool(os.getenv("MDMANSER_PHPSESSID", "").strip())


def _session_id() -> str:
    value = os.getenv("MDMANSER_PHPSESSID", "").strip()
    if not value:
        raise MDManserConfigurationError("MDMANSER_PHPSESSID is not configured")
    return value


def _validate_https(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        raise MDManserConfigurationError("MDMANSER_BASE_URL must use HTTPS")


def _is_authentication_failure(text: str, status_code: int) -> bool:
    lowered = (text or "").lower()
    return (
        status_code in {401, 403}
        or "authentication required" in lowered
        or ("login" in lowered and "password" in lowered)
        or ("login" in lowered and "phpsessid" in lowered)
    )


class MDManserClient:
    def __init__(self, base_url: str | None = None, session_id: str | None = None, timeout: int = 30):
        self.base_url = (base_url or mdmanser_base_url()).rstrip("/")
        _validate_https(self.base_url)
        self.session_id = session_id or _session_id()
        self.timeout = timeout
        self.last_status_code: int | None = None
        self.session = requests.Session()
        self.session.cookies.set("PHPSESSID", self.session_id, domain=MDMANSER_COOKIE_DOMAIN, path="/")

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _checked_response(self, response: requests.Response) -> requests.Response:
        self.last_status_code = response.status_code
        if _is_authentication_failure(response.text, response.status_code):
            raise MDManserAuthenticationError("MDManser authentication required or session expired")
        return response

    def get_calendar_html(self, month: int, year: int) -> str:
        try:
            response = self.session.get(self._url("/"), params={"month": month, "year": year}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise MDManserRequestError(f"MDManser calendar request failed: {exc}") from exc
        return self._checked_response(response).text

    def search_cases(self, payload: dict) -> dict | str:
        endpoint = self._url("/process/other/ajax.php?f=searchCases")
        try:
            response = self.session.post(endpoint, data=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise MDManserRequestError(f"MDManser searchCases request failed: {exc}") from exc
        response = self._checked_response(response)
        try:
            return response.json()
        except ValueError:
            return response.text

    def edit_case(
        self,
        case_id: str,
        new_id: str,
        visit_date: str,
        engineer_id: str,
        note: str,
        followup_date: str,
        followup_time: str,
        status_id: str,
        priority_id: str,
    ) -> dict:
        endpoint = self._url("/process/other/ajax.php?f=editCase")
        record_values = ["", visit_date, "-", engineer_id, note, "-", engineer_id, followup_date, followup_time, status_id, priority_id]
        multipart_fields: list[tuple[str, tuple[None, str]]] = [
            ("case_id", (None, str(case_id))),
            ("new", (None, str(new_id))),
        ]
        multipart_fields.extend(("record[]", (None, str(value))) for value in record_values)
        try:
            response = self.session.post(endpoint, files=multipart_fields, timeout=self.timeout)
        except requests.RequestException as exc:
            raise MDManserRequestError(f"MDManser editCase request failed: {exc}") from exc
        response = self._checked_response(response)
        return {
            "status_code": response.status_code,
            "response_text": response.text,
            "ok": response.ok,
            "endpoint": endpoint,
            "action": "editCase",
        }
