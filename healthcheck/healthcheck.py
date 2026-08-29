import logging

from aiohttp import web
from redbot.core import Config, checks, commands

log = logging.getLogger("red.shadow-cogs.healthcheck")


class HealthCheck(commands.Cog):
    """Expose an HTTP liveness endpoint for external monitoring.

    Serves ``GET /health`` -> ``200 {"status": "ok"}`` so process managers and
    orchestrators (Kubernetes liveness probes, uptime checks) can confirm the
    bot process is alive and its event loop is responsive. The endpoint is
    intentionally dependency-free: it reflects only that the process is running,
    not the health of Discord connectivity or any downstream service.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x5348454C5448)
        self.config.register_global(host="127.0.0.1", port=8080)
        self._runner: web.AppRunner | None = None

    async def cog_load(self) -> None:
        await self._start_server()

    async def cog_unload(self) -> None:
        await self._stop_server()

    async def _start_server(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()

        host = await self.config.host()
        port = await self.config.port()
        site = web.TCPSite(self._runner, host, port)
        await site.start()
        log.info("Health endpoint listening on %s:%s/health", host, port)

    async def _stop_server(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    @commands.group(name="healthcheck")
    @checks.is_owner()
    async def healthcheck(self, ctx):
        """Configure the health endpoint."""

    @healthcheck.command(name="bind")
    async def set_bind(self, ctx, host: str, port: int = 8080):
        """Set the host and port the health endpoint binds to (restart to apply).

        Defaults to 127.0.0.1 (loopback only). In a container or Kubernetes pod,
        set the host to 0.0.0.0 so the probe can reach it from outside.
        """
        await self.config.host.set(host)
        await self.config.port.set(port)
        await ctx.send(f"Health endpoint will bind to `{host}:{port}` on next load.")

    @healthcheck.command(name="restart")
    async def restart_server(self, ctx):
        """Restart the health endpoint to apply a new bind address."""
        await self._stop_server()
        await self._start_server()
        await ctx.tick()
