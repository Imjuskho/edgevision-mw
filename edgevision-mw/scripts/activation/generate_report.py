#!/usr/bin/env python3
"""P4.1 — Generate a municipal weekly report from real data.

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/generate_report.py \
        --node LIL-TRUST-001 \
        --days 7

Produces a CSV + text summary suitable for conversion to PDF.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session


async def get_event_summary(db: AsyncSession, node_id: str, days: int) -> dict:
    """Aggregate events for the given node over the past N days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT
                event_type,
                COUNT(*) as count,
                AVG(confidence) as avg_confidence
            FROM events
            WHERE node_id = :node_id
              AND created_at >= :cutoff
            GROUP BY event_type
            ORDER BY count DESC
        """),
        {"node_id": node_id, "cutoff": cutoff},
    )
    rows = result.fetchall()
    return {
        "event_types": [
            {"type": r[0], "count": r[1], "avg_confidence": round(float(r[2]), 3)}
            for r in rows
        ],
        "total_events": sum(r[1] for r in rows),
    }


async def get_hourly_counts(db: AsyncSession, node_id: str, days: int) -> list[dict]:
    """Get hourly event counts for time-series chart data."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        text("""
            SELECT
                date_trunc('hour', created_at) as hour,
                COUNT(*) as count
            FROM events
            WHERE node_id = :node_id
              AND created_at >= :cutoff
            GROUP BY hour
            ORDER BY hour
        """),
        {"node_id": node_id, "cutoff": cutoff},
    )
    return [{"hour": str(r[0]), "count": r[1]} for r in result.fetchall()]


async def get_scenario_summary(db: AsyncSession, node_id: str, days: int) -> dict:
    """Count scenario cards for this node."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        text("""
            SELECT
                scenario_type,
                COUNT(*) as count,
                AVG(CASE WHEN exported THEN 1 ELSE 0 END) as export_rate
            FROM scenario_cards
            WHERE node_id = :node_id
              AND created_at >= :cutoff
            GROUP BY scenario_type
        """),
        {"node_id": node_id, "cutoff": cutoff},
    )
    rows = result.fetchall()
    return {
        "types": [
            {"type": r[0], "count": r[1], "export_rate": round(float(r[2]), 2)}
            for r in rows
        ],
        "total_scenarios": sum(r[1] for r in rows),
    }


async def get_anomaly_summary(db: AsyncSession, node_id: str, days: int) -> dict:
    """Count anomalies for this node."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        text("""
            SELECT
                anomaly_type,
                COUNT(*) as count,
                AVG(anomaly_score) as avg_score
            FROM anomaly_events
            WHERE camera_node_id = :node_id
              AND created_at >= :cutoff
            GROUP BY anomaly_type
        """),
        {"node_id": node_id, "cutoff": cutoff},
    )
    rows = result.fetchall()
    return {
        "types": [
            {"type": r[0], "count": r[1], "avg_score": round(float(r[2]), 3)}
            for r in rows
        ],
        "total_anomalies": sum(r[1] for r in rows),
    }


async def generate_report(node_id: str, days: int) -> dict:
    """Build the full report data structure."""
    async with async_session() as db:
        events = await get_event_summary(db, node_id, days)
        hourly = await get_hourly_counts(db, node_id, days)
        scenarios = await get_scenario_summary(db, node_id, days)
        anomalies = await get_anomaly_summary(db, node_id, days)

    report = {
        "report_type": "weekly_municipal",
        "node_id": node_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "period_days": days,
        "summary": {
            "total_events": events["total_events"],
            "total_scenarios": scenarios["total_scenarios"],
            "total_anomalies": anomalies["total_anomalies"],
        },
        "events": events,
        "hourly_counts": hourly,
        "scenarios": scenarios,
        "anomalies": anomalies,
    }
    return report


def save_csv(hourly: list[dict], output_dir: Path) -> Path:
    """Save hourly counts as CSV for chart generation."""
    csv_path = output_dir / "hourly_counts.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["hour", "count"])
        writer.writeheader()
        writer.writerows(hourly)
    return csv_path


def print_text_summary(report: dict) -> None:
    """Print a human-readable text summary."""
    s = report["summary"]
    print(f"\n{'=' * 60}")
    print(f"  EDGEVISION-MW WEEKLY REPORT")
    print(f"  Node: {report['node_id']}")
    print(f"  Period: Last {report['period_days']} days")
    print(f"  Generated: {report['generated_at']}")
    print(f"{'=' * 60}")
    print(f"\n  EVENTS:       {s['total_events']} total")
    for e in report["events"]["event_types"]:
        print(f"    {e['type']}: {e['count']} (avg confidence: {e['avg_confidence']:.1%})")
    print(f"\n  SCENARIOS:    {s['total_scenarios']} total")
    for sc in report["scenarios"]["types"]:
        print(f"    {sc['type']}: {sc['count']} (exported: {sc['export_rate']:.0%})")
    print(f"\n  ANOMALIES:    {s['total_anomalies']} total")
    for a in report["anomalies"]["types"]:
        print(f"    {a['type']}: {a['count']} (avg score: {a['avg_score']:.3f})")
    print(f"\n  HOURLY BREAKDOWN:")
    for h in report["hourly_counts"][:24]:
        bar = "█" * min(h["count"], 50)
        print(f"    {h['hour'][:16]}: {h['count']:>4} {bar}")
    print(f"{'=' * 60}\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate municipal weekly report")
    parser.add_argument("--node", default="LIL-TRUST-001", help="Node ID")
    parser.add_argument("--days", type=int, default=7, help="Number of days to include")
    parser.add_argument("--output-dir", default="/tmp/edgevision_exports/reports")
    args = parser.parse_args()

    print(f"[P4.1] Generating report for {args.node} ({args.days} days)")

    report = await generate_report(args.node, args.days)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = output_dir / f"report_{args.node}_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  JSON report: {json_path}")

    # Save CSV
    csv_path = save_csv(report["hourly_counts"], output_dir)
    print(f"  CSV data:    {csv_path}")

    # Print text summary
    print_text_summary(report)


if __name__ == "__main__":
    asyncio.run(main())
