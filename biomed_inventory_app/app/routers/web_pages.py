from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from app import legacy_main

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Web Pages"])


@router.get("/aftermarket", include_in_schema=False)
def aftermarket_page_alias():
    return RedirectResponse("/aftersales", status_code=303)


def _redirect_with_query(request: Request, destination: str) -> RedirectResponse:
    query = request.url.query
    return RedirectResponse(f"{destination}?{query}" if query else destination, status_code=303)


def _canonical_aftersales_section(section: str) -> str:
    section = section.strip("/")
    if section == "pm" or section.startswith("pm/") or section == "pm-tracking" or section.startswith("pm-tracking/"):
        return "/aftersales/preventivemaintenance"
    if section == "service-cases" or section.startswith("service-cases/"):
        return "/aftersales/service-calls"
    if section == "service-history" or section.startswith("service-history/"):
        return "/aftersales/service-calls"
    if section == "training-demo" or section.startswith("training-demo/"):
        return f"/aftersales/trainings/{section.split('/', 1)[1]}".rstrip("/") if "/" in section else "/aftersales/trainings"
    if section == "fmi-recall" or section.startswith("fmi-recall/") or section == "fmi-field-modifications" or section.startswith("fmi-field-modifications/"):
        return f"/aftersales/technical-cases/{section.split('/', 1)[1]}".rstrip("/") if "/" in section else "/aftersales/technical-cases"
    if section == "delivery-installation" or section.startswith("delivery-installation/"):
        return f"/aftersales/installations/{section.split('/', 1)[1]}".rstrip("/") if "/" in section else "/aftersales/installations"
    return f"/aftersales/{section}".rstrip("/")


@router.get("/aftermarket/{section:path}", include_in_schema=False)
def aftermarket_section_alias(section: str, request: Request):
    return _redirect_with_query(request, _canonical_aftersales_section(section))


@router.get("/after-sales", include_in_schema=False)
def after_sales_legacy_alias():
    return RedirectResponse("/aftersales", status_code=303)


@router.get("/after-sales/{section:path}", include_in_schema=False)
def after_sales_legacy_section_alias(section: str, request: Request):
    return _redirect_with_query(request, _canonical_aftersales_section(section))


@router.get("/aftersales/contracts/dashboard", include_in_schema=False)
@router.get("/after-sales/contracts/dashboard", include_in_schema=False)
def aftersales_contracts_dashboard_alias(request: Request):
    return _redirect_with_query(request, "/aftersales/preventivemaintenance")


@router.get("/aftersales/preventivemaintenance", include_in_schema=False)
@router.get("/aftersales/preventivemaintenance/{section:path}", include_in_schema=False)
@router.get("/after-sales/preventivemaintenance", include_in_schema=False)
@router.get("/after-sales/preventivemaintenance/{section:path}", include_in_schema=False)
def aftersales_preventive_maintenance_dashboard(section: str = ""):
    return FileResponse(legacy_main.BASE_DIR / "static" / "pm" / "index.html")


@router.get("/aftersales/contracts", include_in_schema=False)
@router.get("/aftersales/contracts/{section:path}", include_in_schema=False)
@router.get("/after-sales/contracts", include_in_schema=False)
@router.get("/after-sales/contracts/{section:path}", include_in_schema=False)
def aftersales_contracts_page(section: str = ""):
    return FileResponse(legacy_main.BASE_DIR / "static" / "pm" / "index.html")


@router.get("/aftersales/pm", include_in_schema=False)
@router.get("/aftersales/pm/{section:path}", include_in_schema=False)
@router.get("/aftersales/preventive-maintenance", include_in_schema=False)
@router.get("/aftersales/preventive-maintenance/{section:path}", include_in_schema=False)
def aftersales_preventive_maintenance_page(request: Request, section: str = ""):
    return _redirect_with_query(request, "/aftersales/preventivemaintenance")


@router.get("/aftersales/pm-tracking", include_in_schema=False)
def aftersales_pm_tracking_alias(request: Request):
    return _redirect_with_query(request, "/aftersales/preventivemaintenance")


@router.get("/aftersales/pm-tracking/{section:path}", include_in_schema=False)
def aftersales_pm_tracking_section_alias(section: str, request: Request):
    return _redirect_with_query(request, "/aftersales/preventivemaintenance")


@router.get("/aftersales/service-cases", include_in_schema=False)
def aftersales_service_cases_alias(request: Request):
    return _redirect_with_query(request, "/aftersales/service-calls")


@router.get("/aftersales/service-history", include_in_schema=False)
@router.get("/aftersales/service-history/{section:path}", include_in_schema=False)
def aftersales_service_history_alias(request: Request, section: str = ""):
    suffix = f"&view={section}" if section and request.url.query else f"?view={section}" if section else ""
    target = "/aftersales/service-calls"
    if suffix:
        return RedirectResponse(f"{target}{'?' + request.url.query if request.url.query else ''}{suffix}", status_code=303)
    return _redirect_with_query(request, target)


@router.get("/aftersales/training-demo", include_in_schema=False)
@router.get("/aftersales/training-demo/{section:path}", include_in_schema=False)
def aftersales_training_demo_alias(request: Request, section: str = ""):
    return _redirect_with_query(request, f"/aftersales/trainings/{section}".rstrip("/"))


@router.get("/aftersales/fmi-recall", include_in_schema=False)
@router.get("/aftersales/fmi-recall/{section:path}", include_in_schema=False)
@router.get("/aftersales/fmi-field-modifications", include_in_schema=False)
@router.get("/aftersales/fmi-field-modifications/{section:path}", include_in_schema=False)
def aftersales_fmi_alias(request: Request, section: str = ""):
    return _redirect_with_query(request, f"/aftersales/technical-cases/{section}".rstrip("/"))


@router.get("/aftersales/delivery-installation", include_in_schema=False)
@router.get("/aftersales/delivery-installation/{section:path}", include_in_schema=False)
def aftersales_delivery_installation_alias(request: Request, section: str = ""):
    return _redirect_with_query(request, f"/aftersales/installations/{section}".rstrip("/"))


@router.get("/aftersales/schedule", include_in_schema=False)
@router.get("/after-sales/schedule", include_in_schema=False)
def aftersales_schedule_page():
    return FileResponse(legacy_main.BASE_DIR / "static" / "engineer_schedule.html")


@router.get("/aftersales/schedule/engineers/{engineer_id}", include_in_schema=False)
@router.get("/after-sales/schedule/engineers/{engineer_id}", include_in_schema=False)
def aftersales_engineer_schedule_page(engineer_id: int):
    return FileResponse(legacy_main.BASE_DIR / "static" / "engineer_schedule.html")


@router.get("/sales-cases", include_in_schema=False)
def sales_cases_alias():
    return RedirectResponse("/sales", status_code=303)


@router.get("/crm/contacts", include_in_schema=False)
def crm_contacts_page():
    return FileResponse(legacy_main.BASE_DIR / "static" / "crm_contacts.html")


@router.get("/crm/contacts/{contact_id}", include_in_schema=False)
def crm_contact_detail_page(contact_id: int):
    return FileResponse(legacy_main.BASE_DIR / "static" / "crm_contacts.html")


def _is_web_page(path: str) -> bool:
    return not path.startswith("/api") and not path.startswith("/quotations")


mount_legacy_routes(router, _is_web_page)
