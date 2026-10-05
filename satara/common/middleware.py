"""Middleware for a web application."""

from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


class PathBodyLimitMiddleware:
    """Limits the size of a request body on one path, leaving other paths as they are."""

    def __init__(self, app: ASGIApp, path: str, max_body_size: int) -> None:
        """Set up the limit.

        Args:
            app: The application to pass requests on to.
            path: The path whose requests are limited.
            max_body_size: The largest body allowed on that path, in bytes.
        """
        self._app = app
        self._limited = RequestBodyLimitMiddleware(app, max_body_size=max_body_size)
        self._path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, through the limit if it is for the path."""
        path, root_path = scope.get("path", ""), scope.get("root_path", "")
        # The path includes the prefix the application is served under, if any; the prefix is
        # removed only where it ends at a segment boundary, as the router does.
        if root_path and path.startswith(f"{root_path}/"):
            path = path.removeprefix(root_path)
        is_limited = scope["type"] == "http" and path == self._path
        await (self._limited if is_limited else self._app)(scope, receive, send)
