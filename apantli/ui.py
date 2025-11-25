from fastapi import Request

from fastapi.templating import Jinja2Templates

from apantli.auth import authenticated_route, authenticated_ui_route

# Templates
templates = Jinja2Templates(directory="templates")


@authenticated_ui_route
async def dashboard(request: Request):
    """Simple HTML dashboard."""
    response = templates.TemplateResponse("dashboard.html", {"request": request})
    # Prevent browser caching of the HTML to avoid stale UI bugs
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@authenticated_ui_route
async def compare_page(request: Request):
    """Chat comparison interface for testing multiple models side-by-side."""
    response = templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "models": list(request.app.state.model_map.keys())
        }
    )
    # Prevent browser caching of the HTML to avoid stale UI bugs
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
