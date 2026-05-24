from __future__ import annotations

import os
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_MDMANSER_BASE_URL = "https://cmm.mdmanser.com"
MDMANSER_COOKIE_DOMAIN = "cmm.mdmanser.com"
CALENDAR_PATH = "/en/calendar/calendar/"


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


def mdmanser_timeout() -> int:
    value = os.getenv("MDMANSER_TIMEOUT", "20").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 20


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
    def __init__(self, base_url: str | None = None, session_id: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or mdmanser_base_url()).rstrip("/")
        _validate_https(self.base_url)
        self.session_id = session_id or _session_id()
        self.timeout = timeout or mdmanser_timeout()
        self.last_status_code: int | None = None
        self.session = requests.Session()
        self.session.cookies.set("PHPSESSID", self.session_id, domain=MDMANSER_COOKIE_DOMAIN, path="/")
        self.session.headers.update(
            {
                "User-Agent": "IRM-ERP-MDManser-ReadConnector/1.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": self._url(CALENDAR_PATH),
            }
        )

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _checked_response(self, response: requests.Response) -> requests.Response:
        self.last_status_code = response.status_code
        if _is_authentication_failure(response.text, response.status_code):
            raise MDManserAuthenticationError("MDManser authentication required or session expired")
        return response

    @classmethod
    def configured(cls) -> bool:
        return bool(mdmanser_base_url()) and mdmanser_session_configured()

    def get_calendar_html(self, month: int, year: int) -> str:
        try:
            response = self.session.get(self._url(CALENDAR_PATH), params={"m": month, "y": year}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise MDManserRequestError(f"MDManser calendar request failed: {exc}") from exc
        return self._checked_response(response).text

    def check_calendar_read(self, month: int, year: int) -> dict:
        html = self.get_calendar_html(month=month, year=year)
        lowered = html.lower()
        return {
            "configured": self.configured(),
            "auth_ok": True,
            "status_code": self.last_status_code or 200,
            "html_length": len(html),
            "contains_service_contract": "serviceContract" in html,
            "contains_engineer": "engineer" in lowered,
            "contains_callreassons": "callreassons" in lowered,
            "contains_calendar": "calendar" in lowered,
        }
