#!/usr/bin/env python3
"""Round-robin API keys onto upstream OpenAI-compatible requests.

Reads a JSON list of keys from KEYS_FILE. Replaces / sets Authorization
per request. Still a toy — no backoff, no quarantine of bad keys.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
from pathlib import Path

from aiohttp import web, ClientSession, ClientTimeout, TCPConnector

log = logging.getLogger("key_rotate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

UPSTREAM = os.environ.get("UPSTREAM", "https://api.openai.com").rstrip("/")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "18080"))
KEYS_FILE = os.environ.get("KEYS_FILE", "examples/keys.example.json")


def load_keys(path: str) -> list[str]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        keys = data.get("keys") or data.get("api_keys") or []
    else:
        keys = data
    keys = [k.strip() for k in keys if isinstance(k, str) and k.strip()]
    if not keys:
        raise SystemExit(f"no keys found in {path}")
    return keys


async def handle(request: web.Request) -> web.StreamResponse:
    key = next(request.app["key_cycle"])
    path = request.path_qs
    url = f"{UPSTREAM}{path}"
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length", "authorization")}
    headers["Authorization"] = f"Bearer {key}"

    body = await request.read()
    timeout = ClientTimeout(total=None, sock_connect=30, sock_read=None)
    session: ClientSession = request.app["session"]

    async with session.request(
        request.method, url, headers=headers, data=body, timeout=timeout
    ) as resp:
        out = web.StreamResponse(status=resp.status, reason=resp.reason)
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
    keys = load_keys(KEYS_FILE)
    app["key_cycle"] = itertools.cycle(keys)
    app["session"] = ClientSession(connector=TCPConnector(limit=64))
    log.info("loaded %d keys from %s", len(keys), KEYS_FILE)


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def main() -> None:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", handle)
    log.info("listening on http://%s:%s -> %s (rotating keys)", LISTEN_HOST, LISTEN_PORT, UPSTREAM)
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT, print=None)


if __name__ == "__main__":
    main()
