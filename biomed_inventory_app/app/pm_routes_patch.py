# Add this to app/main.py after BASE_DIR is defined and after auth helpers exist.
# It serves the built PM React module from app/static/pm/index.html.

from fastapi.responses import FileResponse

@app.get('/pm')
def pm_module_page():
    # If your app has require_login(), call it before returning this page.
    # Example: require_login(request)
    return FileResponse(BASE_DIR / 'static' / 'pm' / 'index.html')

@app.get('/pm/{full_path:path}')
def pm_module_spa_fallback(full_path: str):
    # Allows React/Vite routes under /pm to refresh safely.
    return FileResponse(BASE_DIR / 'static' / 'pm' / 'index.html')

@app.get('/api/pm/health')
def pm_health():
    return {'module': 'pm', 'status': 'ok'}
