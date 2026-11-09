#!/usr/bin/env python3
"""Dumb localhost reverse proxy for OpenAI-compatible HTTP APIs.

Forwards path + query + body. Optionally injects Authorization if the client
didn't send one. Bind to 127.0.0.1 by default — don't expose this blindly.
"""
from __future__ import annotations

import os
import logging
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector

log = logging.getLogger("simple_forward")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8080").rstrip("/")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "18080"))
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")


async def handle(request: web.Request) -> web.StreamResponse:
    path = request.path_qs
    url = f"{UPSTREAM}{path}"
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    if UPSTREAM_API_KEY and "authorization" not in {h.lower() for h in headers}:
        headers["Authorization"] = f"Bearer {UPSTREAM_API_KEY}"

    body = await request.read()
    timeout = ClientTimeout(total=None, sock_connect=30, sock_read=None)
    session: ClientSession = request.app["session"]

    async with session.request(
        request.method, url, headers=headers, data=body, timeout=timeout
    ) as resp:
        out = web.StreamResponse(status=resp.status, reason=resp.reason)
        # pass through most headers; hop-by-hop ones skipped loosely
        for k, v in resp.headers.items():
            if k.lower() in ("transfer-encoding", "content-encoding", "content-length"):
                continue
            out.headers[k] = v
        await out.prepare(request)
        async for chunk in resp.content.iter_chunked(64 * 1024):
            await out.write(chunk)
        await out.write_eof()
        return out


async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession(connector=TCPConnector(limit=64))


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def main() -> None:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", handle)
    log.info("listening on http://%s:%s -> %s", LISTEN_HOST, LISTEN_PORT, UPSTREAM)
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT, print=None)


if __name__ == "__main__":
    main()
