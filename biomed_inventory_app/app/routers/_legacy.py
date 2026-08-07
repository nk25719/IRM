from collections.abc import Callable

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app import legacy_main


def mount_legacy_routes(router: APIRouter, matches: Callable[[str], bool]) -> None:
    """Attach selected legacy routes while route handlers are being untangled."""
    mounted_paths = {route.path for route in router.routes if isinstance(route, APIRoute)}
    for route in legacy_main.app.routes:
        if isinstance(route, APIRoute) and matches(route.path) and route.path not in mounted_paths:
            router.routes.append(route)
            mounted_paths.add(route.path)
