"""Transport contract fixture; not installed or exposed by the product."""
import sys
import os
from mcp.server.fastmcp import FastMCP

app = FastMCP("transport-contract", host="127.0.0.1", port=int(sys.argv[1]), log_level="ERROR")


@app.tool()
def inspect_value(value: str) -> dict:
    """Return the value received by the real HTTP server."""
    return {"observed": value}


if __name__ == "__main__":
    if os.environ.get("PI_FIXTURE_TOKEN"):
        import uvicorn
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import Response
        async def authenticate(request, call_next):
            if request.headers.get("Authorization") != "Bearer " + os.environ["PI_FIXTURE_TOKEN"]:
                return Response(status_code=401)
            return await call_next(request)
        http = app.streamable_http_app()
        http.add_middleware(BaseHTTPMiddleware, dispatch=authenticate)
        uvicorn.run(http, host="127.0.0.1", port=int(sys.argv[1]), log_level="error")
    else:
        app.run(transport="streamable-http")
