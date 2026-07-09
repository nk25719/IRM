from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Web Pages"])


@router.get("/aftermarket", include_in_schema=False)
def aftermarket_page_alias():
    return RedirectResponse("/aftersales", status_code=303)


@router.get("/aftermarket/{section:path}", include_in_schema=False)
def aftermarket_section_alias(section: str):
    return RedirectResponse(f"/aftersales/{section}", status_code=303)


def _is_web_page(path: str) -> bool:
    return not path.startswith("/api") and not path.startswith("/quotations")


mount_legacy_routes(router, _is_web_page)
