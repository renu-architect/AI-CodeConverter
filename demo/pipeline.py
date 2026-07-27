"""Simulate migration pipeline stages without Claude API calls."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from demo.constants import DEMO_STAGES
from demo.output_runner import OutputComparisonReport, build_output_comparison

EventCallback = Callable[[dict[str, Any]], None]


async def run_demo_pipeline(
    *,
    job_name: str,
    on_event: EventCallback,
    stage_delay_seconds: float = 0.35,
) -> OutputComparisonReport:
    """Emit staged workflow events and run output parity check at TESTING."""
    report: OutputComparisonReport | None = None

    def ts() -> str:
        return datetime.now().strftime("%H:%M:%S")

    for stage, event_type, message in DEMO_STAGES:
        if stage == "TESTING":
            on_event(
                {
                    "timestamp": ts(),
                    "stage": stage,
                    "type": "stage_start",
                    "message": "Running sample data through Glue vs Synapse transforms",
                    "metadata": {},
                }
            )
            await asyncio.sleep(stage_delay_seconds)
            report = build_output_comparison(job_name=job_name)
            on_event(
                {
                    "timestamp": ts(),
                    "stage": stage,
                    "type": event_type,
                    "message": report.message,
                    "metadata": report.model_dump(),
                }
            )
            await asyncio.sleep(stage_delay_seconds)
            continue

        on_event(
            {
                "timestamp": ts(),
                "stage": stage,
                "type": event_type,
                "message": message,
                "metadata": {},
            }
        )
        await asyncio.sleep(stage_delay_seconds)

    return report or build_output_comparison(job_name=job_name)
