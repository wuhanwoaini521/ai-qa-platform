from app.ports.database_health import DatabaseHealthProbe


class HealthService:
    def __init__(self, database_health_probe: DatabaseHealthProbe) -> None:
        self.database_health_probe = database_health_probe

    async def database_is_healthy(self) -> bool:
        result = await self.database_health_probe.check()
        return result["status"] == "ok"
