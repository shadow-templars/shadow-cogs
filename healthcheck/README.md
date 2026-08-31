# HealthCheck

> **Deprecated / not actively maintained.** This works and we still run it, but for
> a general-purpose liveness endpoint we now recommend
> [Vexed's `uptimeresponder`](https://cogdocs.vexcodes.com/en/latest/cogs/uptimeresponder.html),
> which is actively maintained and does the same job. Prefer that for new setups.
>
> Longer term we think a proper health mechanism fits best in Red core — a
> process-level endpoint that exists before cogs load, and that cogs can register
> their own readiness into. There's an open discussion at
> [Cog-Creators/Red-DiscordBot#6802](https://github.com/Cog-Creators/Red-DiscordBot/issues/6802);
> worth a read (and a reaction) if that resonates with how you run your bot.

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
