"""Middleware for a web application."""

from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class PathBodyLimitMiddleware:
    """Limits the size of a request body on one API path, leaving other paths as they are.

    The API path is the one the application's routes match: without the prefix the application
    is served under, and without the query string. Only that exact path is limited, whatever
    the method; paths below it are not.
    """

    def __init__(self, app: ASGIApp, path: str, max_body_size: int) -> None:
        """Set up the limit.

        Args:
            app: The application to pass requests on to.
            path: The API path whose requests are limited.
            max_body_size: The largest body allowed on that path, in bytes.
        """
        self._app = app
        self._limited = RequestBodyLimitMiddleware(app, max_body_size=max_body_size)
        self._path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, through the limit if it is for the API path."""
        full_path, root_path = scope.get("path", ""), scope.get("root_path", "")
        # The full path includes the prefix the application is served under, if any; the
        # prefix is removed only where it ends at a segment boundary, as the router does.
        api_path = full_path
        if root_path and full_path.startswith(f"{root_path}/"):
            api_path = full_path.removeprefix(root_path)
        is_limited = scope["type"] == "http" and api_path == self._path
        await (self._limited if is_limited else self._app)(scope, receive, send)
