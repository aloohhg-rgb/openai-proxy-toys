# openai-proxy-toys

Tiny local toys for talking to OpenAI-compatible backends without crying.

I run a few different local servers (llama-server, vLLM, whatever is up that week) and got sick of rewriting base URLs / stuffing API keys into every client. This is a handful of small reverse-proxy helpers — not a product, not HA, not multi-tenant.

**Use case:** point Cursor / Open WebUI / a one-off script at `http://127.0.0.1:18080` and let this thing fan out.

## toys

| path | what |
|------|------|
| `proxy/simple_forward.py` | dumb reverse proxy + optional bearer inject |
| `proxy/key_rotate.py` | round-robin a list of keys onto upstream requests |
| `proxy/multi_backend.py` | route by `model` prefix to different upstreams |
| `examples/` | sample configs / curl |
| `scripts/smoke.sh` | hit `/v1/models` through the proxy |

## quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# forward everything to a local llama-server
UPSTREAM=http://127.0.0.1:8080 python proxy/simple_forward.py

# or rotate keys (for a remote OpenAI-compatible host)
KEYS_FILE=examples/keys.example.json UPSTREAM=https://api.example.com \
  python proxy/key_rotate.py
```

Don't commit real keys. `examples/keys.example.json` is fake.

## caveats

- streaming is best-effort (I pass through chunked responses; edge cases exist)
- no auth on the *listen* side — bind localhost only unless you know what you're doing
- this is weekend code. read it before you put it anywhere interesting

## license

MIT.
