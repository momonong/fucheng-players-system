from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time

import httpx
import psutil


async def run(args: argparse.Namespace) -> None:
    latencies: list[float] = []
    errors: list[str] = []
    writer_client: httpx.AsyncClient | None = None
    writer_csrf = ""
    if args.admin_username:
        writer_client = httpx.AsyncClient(base_url=args.url, timeout=30)
        try:
            login = await writer_client.post("/api/auth/login", json={"username": args.admin_username, "password": args.admin_password})
            login.raise_for_status()
            writer_csrf = login.json()["csrf_token"]
        except Exception:
            await writer_client.aclose()
            raise
    stop_at = time.monotonic() + args.duration

    async def reader(number: int) -> None:
        rng = random.Random(number)
        await asyncio.sleep(args.ramp * number / max(1, args.users - 1))
        async with httpx.AsyncClient(base_url=args.url, timeout=30) as client:
            while time.monotonic() < stop_at:
                started = time.perf_counter()
                try:
                    response = await client.get("/api/public/members", params={"level": rng.randint(1, 10)})
                    response.raise_for_status()
                    latencies.append((time.perf_counter() - started) * 1000)
                except Exception as error:  # 統一收集壓測錯誤，不中斷其他使用者
                    errors.append(f"reader-{number}: {error}")
                await asyncio.sleep(rng.uniform(args.pause_min, args.pause_max))

    async def writer() -> None:
        if not writer_client:
            return
        try:
            sequence = 0
            while time.monotonic() < stop_at:
                await asyncio.sleep(args.write_interval)
                sequence += 1
                started = time.perf_counter()
                try:
                    response = await writer_client.post(
                        "/api/admin/members",
                        headers={"X-CSRF-Token": writer_csrf},
                        json={
                            "name": f"負載測試會員 {sequence}", "distinguishing_note": "合成資料",
                            "legacy_number": f"LOAD-{int(started)}-{sequence}", "level": sequence % 10 + 1,
                            "diet": "unset", "is_active": True,
                        },
                    )
                    response.raise_for_status()
                    latencies.append((time.perf_counter() - started) * 1000)
                except Exception as error:
                    errors.append(f"writer: {error}")
        finally:
            await writer_client.aclose()

    process = psutil.Process(args.pid) if args.pid else None
    start_cpu = process.cpu_times() if process else None
    start = time.monotonic()
    await asyncio.gather(*(reader(i) for i in range(args.users)), writer())
    elapsed = time.monotonic() - start
    ordered = sorted(latencies)

    def percentile(ratio: float) -> float:
        return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))] if ordered else 0

    print(f"users={args.users} duration_s={elapsed:.1f} requests={len(latencies) + len(errors)} errors={len(errors)} error_rate={len(errors) / max(1, len(latencies) + len(errors)):.4%}")
    print(f"latency_ms p50={percentile(.50):.1f} p95={percentile(.95):.1f} p99={percentile(.99):.1f} max={max(ordered, default=0):.1f}")
    if process and start_cpu:
        end_cpu = process.cpu_times()
        cpu_seconds = (end_cpu.user + end_cpu.system) - (start_cpu.user + start_cpu.system)
        print(f"server_rss_mib={process.memory_info().rss / 1024 / 1024:.1f} server_cpu_seconds={cpu_seconds:.2f}")
    if errors:
        print("first_errors:")
        print("\n".join(errors[:10]))


def main() -> None:
    parser = argparse.ArgumentParser(description="府城球館可重現混合負載測試")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--pause-min", type=float, default=0.8)
    parser.add_argument("--pause-max", type=float, default=2.5)
    parser.add_argument("--ramp", type=float, default=10, help="將所有使用者逐步啟動所需秒數")
    parser.add_argument("--admin-username")
    parser.add_argument("--admin-password")
    parser.add_argument("--write-interval", type=float, default=5)
    parser.add_argument("--pid", type=int, help="伺服器 PID，用於量測 RSS 與 CPU 秒數")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
