from __future__ import annotations

import asyncio

import httpx


def test_concurrent_public_reads_release_database_connections(app) -> None:
    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=5) as client:
            responses = await asyncio.wait_for(
                asyncio.gather(*(client.get("/api/public/members") for _ in range(50))),
                timeout=8,
            )
        assert all(response.status_code == 200 for response in responses)

    asyncio.run(exercise())
