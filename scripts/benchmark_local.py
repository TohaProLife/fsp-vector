"""Bounded real HTTP read benchmark; synthetic localhost credentials only."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import time
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(values) * percentile) - 1)], 2)


async def run(base: str, samples: int, concurrency: int) -> dict:
    target = urlparse(base)
    if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost"} or target.username or target.query:
        raise RuntimeError("Only loopback HTTP targets are supported")
    async with httpx.AsyncClient(base_url=base, timeout=20, follow_redirects=False, trust_env=False) as client:
        health = (await client.get("/health")).json()
        if health.get("environment") != "local_demo":
            raise RuntimeError("This benchmark requires the explicit synthetic local demo")
        login = await client.post("/api/v1/auth/login", json={"email":"employer@vector.local","password":"VectorDemo2026!"})
        login.raise_for_status()
        limits = asyncio.Semaphore(concurrency)
        paths = ["/api/v1/employer/candidates?page=1", "/api/v1/employer/candidates?specialization=frontend&grade=intern",
                 "/api/v1/employer/categories", "/api/v1/employer/dashboard"]
        for path in paths:
            response = await client.get(path)
            response.raise_for_status()
        errors: list[dict] = []
        measurements: list[dict] = []

        async def one(number: int) -> None:
            path = paths[number % len(paths)]
            async with limits:
                started = time.perf_counter()
                try:
                    response = await client.get(path)
                    milliseconds = (time.perf_counter() - started) * 1000
                    measurements.append({"route":path,"ms":milliseconds,"status":response.status_code})
                    if response.status_code != 200:
                        errors.append({"route":path,"status":response.status_code})
                except httpx.HTTPError as exc:
                    errors.append({"route":path,"error":type(exc).__name__})

        started = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(samples)))
        elapsed = time.perf_counter() - started
        summary = {}
        for path in paths:
            timings = [item["ms"] for item in measurements if item["route"] == path]
            if timings:
                summary[path] = {"requests":len(timings),"p50_ms":percentile(timings,.5),"p95_ms":percentile(timings,.95),
                                 "p99_ms":percentile(timings,.99),"mean_ms":round(statistics.mean(timings),2)}
        inventory = (await client.get("/api/v1/employer/candidates?page=1")).json()
        return {"status":"passed" if not errors else "failed", "measured_at":datetime.now(timezone.utc).isoformat(),
                "environment":health["environment"],"database":health["database"],"os":platform.system(),
                "workload":"real_authenticated_HTTP_reads", "requests":samples,"concurrency":concurrency,
                "elapsed_seconds":round(elapsed,3),"requests_per_second":round(samples/elapsed,2),
                "published_candidate_count":inventory.get("total"),"routes":summary,"errors":errors,
                "source_sha256":{str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((ROOT/"services/api/app").rglob("*.py"))},
                "limitations":["Synthetic demo population; not a production scale capacity claim",
                               "Read workload only; does not measure exam grading or ranking writes",
                               "Local loopback and existing connection pool; warm-up excluded"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--report", type=Path, default=ROOT/"docs/audits/http-benchmark.json")
    args = parser.parse_args()
    if not 20 <= args.samples <= 500 or not 1 <= args.concurrency <= 16:
        parser.error("Use 20..500 requests and 1..16 concurrent readers")
    report = asyncio.run(run(args.base.rstrip("/"), args.samples, args.concurrency))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({k:v for k,v in report.items() if k!="source_sha256"},ensure_ascii=False,indent=2))
    if report["status"] != "passed":raise SystemExit(1)


if __name__ == "__main__":main()
