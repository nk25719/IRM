from fastapi import APIRouter

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Web Pages"])


def _is_web_page(path: str) -> bool:
    return not path.startswith("/api") and not path.startswith("/quotations")


mount_legacy_routes(router, _is_web_page)
