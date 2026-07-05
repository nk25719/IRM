from collections.abc import Callable

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app import legacy_main


def mount_legacy_routes(router: APIRouter, matches: Callable[[str], bool]) -> None:
    """Attach selected legacy routes while route handlers are being untangled."""
    for route in legacy_main.app.routes:
        if isinstance(route, APIRoute) and matches(route.path):
            router.routes.append(route)
