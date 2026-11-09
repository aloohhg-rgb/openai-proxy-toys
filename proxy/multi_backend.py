#!/usr/bin/env python3
"""Route by model name prefix to different upstreams.

Config JSON shape:
{
  "default": "http://127.0.0.1:8080",
  "routes": [
    {"prefix": "gpt-", "upstream": "https://api.openai.com"},
    {"prefix": "local-", "upstream": "http://127.0.0.1:8080", "strip_prefix": true}
  ]
}

strip_prefix: if true, rewrite model "local-foo" -> "foo" before forwarding.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from aiohttp import web, ClientSession, ClientTimeout, TCPConnector

log = logging.getLogger("multi_backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

LISTEN_HOST = os.environ.get("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "18080"))
ROUTES_FILE = os.environ.get("ROUTES_FILE", "examples/routes.example.json")


def load_routes(path: str) -> dict:
    return json.loads(Path(path).read_text())


def pick_upstream(cfg: dict, model: str | None) -> tuple[str, str | None]:
    """Return (upstream_base, rewritten_model_or_None)."""
    if model:
        for rule in cfg.get("routes") or []:
            prefix = rule.get("prefix") or ""
            if prefix and model.startswith(prefix):
                new_model = model
                if rule.get("strip_prefix"):
                    new_model = model[len(prefix):]
                return rule["upstream"].rstrip("/"), new_model
    return cfg["default"].rstrip("/"), None


async def handle(request: web.Request) -> web.StreamResponse:
    cfg = request.app["cfg"]
    body = await request.read()
    model = None
    rewritten = None
    new_body = body

    if body and "json" in (request.content_type or ""):
        try:
            payload = json.loads(body)
            model = payload.get("model")
            upstream, rewritten = pick_upstream(cfg, model)
            if rewritten is not None and rewritten != model:
                payload["model"] = rewritten
                new_body = json.dumps(payload).encode()
            else:
                upstream, _ = pick_upstream(cfg, model)
        except json.JSONDecodeError:
            upstream = cfg["default"].rstrip("/")
    else:
        upstream = cfg["default"].rstrip("/")

    url = f"{upstream}{request.path_qs}"
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    timeout = ClientTimeout(total=None, sock_connect=30, sock_read=None)
    session: ClientSession = request.app["session"]

    log.info("%s %s model=%s -> %s", request.method, request.path, model, upstream)

    async with session.request(
        request.method, url, headers=headers, data=new_body, timeout=timeout
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
    app["cfg"] = load_routes(ROUTES_FILE)
    app["session"] = ClientSession(connector=TCPConnector(limit=64))
    log.info("routes from %s — default=%s", ROUTES_FILE, app["cfg"].get("default"))


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def main() -> None:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", "/{path:.*}", handle)
    log.info("listening on http://%s:%s", LISTEN_HOST, LISTEN_PORT)
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT, print=None)


if __name__ == "__main__":
    main()
