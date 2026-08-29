from unittest.mock import MagicMock


class TestHealthEndpoint:
    async def test_returns_ok_status(self, healthcheck_cog):
        request = MagicMock()

        response = await healthcheck_cog._handle_health(request)

        assert response.status == 200
        assert response.body == b'{"status": "ok"}'

    async def test_content_type_is_json(self, healthcheck_cog):
        response = await healthcheck_cog._handle_health(MagicMock())

        assert response.content_type == "application/json"


class TestServerLifecycle:
    async def test_start_creates_runner(self, healthcheck_cog):
        await healthcheck_cog._start_server()

        assert healthcheck_cog._runner is not None

        await healthcheck_cog._stop_server()

    async def test_stop_clears_runner(self, healthcheck_cog):
        await healthcheck_cog._start_server()
        await healthcheck_cog._stop_server()

        assert healthcheck_cog._runner is None

    async def test_stop_is_safe_when_not_started(self, healthcheck_cog):
        assert healthcheck_cog._runner is None

        await healthcheck_cog._stop_server()

        assert healthcheck_cog._runner is None

    async def test_binds_to_configured_host_and_port(self, healthcheck_cog):
        healthcheck_cog.config.host.return_value = "127.0.0.1"
        healthcheck_cog.config.port.return_value = 0  # ephemeral port, avoids collisions

        await healthcheck_cog._start_server()

        assert healthcheck_cog._runner is not None
        healthcheck_cog.config.host.assert_awaited()
        healthcheck_cog.config.port.assert_awaited()

        await healthcheck_cog._stop_server()

    async def test_serves_health_over_http(self, healthcheck_cog):
        import aiohttp

        healthcheck_cog.config.host.return_value = "127.0.0.1"
        healthcheck_cog.config.port.return_value = 18099

        await healthcheck_cog._start_server()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://127.0.0.1:18099/health") as resp:
                    assert resp.status == 200
                    assert await resp.json() == {"status": "ok"}
        finally:
            await healthcheck_cog._stop_server()
