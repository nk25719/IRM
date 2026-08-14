from collections.abc import Callable

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app import legacy_main


def mount_legacy_routes(router: APIRouter, matches: Callable[[str], bool]) -> None:
    """Attach selected legacy routes while route handlers are being untangled."""
    mounted_routes = {
        (route.path, frozenset(route.methods or set()))
        for route in router.routes
        if isinstance(route, APIRoute)
    }
    for route in legacy_main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        route_key = (route.path, frozenset(route.methods or set()))
        if matches(route.path) and route_key not in mounted_routes:
            router.routes.append(route)
            mounted_routes.add(route_key)
