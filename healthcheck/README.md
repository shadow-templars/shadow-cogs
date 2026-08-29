# HealthCheck

Exposes an HTTP **liveness** endpoint so process managers and orchestrators can
confirm the bot process is alive.

```
GET /health  ->  200  {"status": "ok"}
```

The endpoint is **dependency-free by design** — it reflects only that the process
is running and its event loop is responsive. It intentionally does **not** check
Discord connectivity or any downstream service: a liveness probe that failed on a
transient Discord blip would cause an orchestrator to needlessly restart a healthy
bot.

## Configuration

Binds to `127.0.0.1:8080` by default (loopback only — safe on a shared host).

```
[p]healthcheck bind <host> [port]   # e.g. bind 0.0.0.0 8080
[p]healthcheck restart              # apply a new bind address
```

> **Containers / Kubernetes:** set the host to `0.0.0.0` so the probe can reach
> the endpoint from outside the container:
>
> ```
> [p]healthcheck bind 0.0.0.0 8080
> [p]healthcheck restart
> ```

## Kubernetes example

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
```

## Requirements

None beyond Red itself — the endpoint is served with `aiohttp`, which ships with
Red (via discord.py).

## Scope

This cog provides **liveness** only. Readiness (are dependencies reachable?) and
per-dependency reporting are deliberately out of scope for this minimal version.
