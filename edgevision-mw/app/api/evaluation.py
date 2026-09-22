"""Evaluation API — run model evaluations, benchmarks, and view past results."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.evaluation_harness import (
    EvalResult,
    measure_inference_time,
    run_benchmark,
    run_evaluation,
)

evaluation_router = APIRouter(prefix="/evaluation", tags=["Evaluation"])

_EVAL_RESULTS_FILE = "/tmp/edgevision_exports/evaluation_results.json"


def _load_eval_results() -> list[dict[str, Any]]:
    """Load persisted evaluation results from disk; empty list if file missing."""
    try:
        if os.path.isfile(_EVAL_RESULTS_FILE):
            with open(_EVAL_RESULTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_eval_result(result: dict[str, Any]) -> None:
    """Append a single evaluation result to the persisted JSON file."""
    os.makedirs(os.path.dirname(_EVAL_RESULTS_FILE), exist_ok=True)
    results = _load_eval_results()
    results.append(result)
    with open(_EVAL_RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)


class PredictionItem(BaseModel):
    class_name: str
    bbox: list[float] = Field(..., description="[x1, y1, x2, y2]")
    confidence: float = 0.0
    image_id: str = ""


class GroundTruthItem(BaseModel):
    class_name: str
    bbox: list[float] = Field(..., description="[x1, y1, x2, y2]")
    image_id: str = ""


class RunEvaluationRequest(BaseModel):
    predictions: list[PredictionItem]
    ground_truths: list[GroundTruthItem]
    model_version: str = "unknown"
    benchmark_name: str = "default"
    iou_threshold: float = 0.5
    regression_threshold: float = 0.02


class BenchmarkSample(BaseModel):
    predictions: list[PredictionItem]
    ground_truths: list[GroundTruthItem]


class RunBenchmarkRequest(BaseModel):
    samples: list[BenchmarkSample]
    model_version: str = "unknown"
    benchmark_name: str = "default"
    iou_threshold: float = 0.5
    regression_threshold: float = 0.02


def _eval_to_dict(result: EvalResult) -> dict[str, Any]:
    return {
        "model_version": result.model_version,
        "benchmark_name": result.benchmark_name,
        "total_samples": result.total_samples,
        "mAP50": result.mAP50,
        "mAP50_95": result.mAP50_95,
        "precision": result.precision,
        "recall": result.recall,
        "f1_score": result.f1_score,
        "per_class_ap": result.per_class_ap,
        "confusion_matrix": result.confusion_matrix,
        "inference_time_ms_avg": result.inference_time_ms_avg,
        "regression_detected": result.regression_detected,
        "regression_details": result.regression_details,
        "passed": result.passed,
        "timestamp": result.timestamp,
    }


@evaluation_router.post("/run")
async def run_eval_endpoint(req: RunEvaluationRequest) -> dict[str, Any]:
    """Run evaluation on a set of predictions vs ground truths."""
    preds = [p.model_dump() for p in req.predictions]
    gts = [g.model_dump() for g in req.ground_truths]

    result = run_evaluation(
        predictions=preds,
        ground_truths=gts,
        model_version=req.model_version,
        benchmark_name=req.benchmark_name,
        iou_threshold=req.iou_threshold,
        regression_threshold=req.regression_threshold,
    )

    result_dict = _eval_to_dict(result)
    _save_eval_result(result_dict)
    return result_dict


@evaluation_router.post("/benchmark")
async def run_benchmark_endpoint(req: RunBenchmarkRequest) -> dict[str, Any]:
    """Run full benchmark across multiple samples and return aggregated results."""
    samples = [
        ([p.model_dump() for p in s.predictions], [g.model_dump() for g in s.ground_truths])
        for s in req.samples
    ]

    result = run_benchmark(
        samples=samples,
        model_version=req.model_version,
        benchmark_name=req.benchmark_name,
        iou_threshold=req.iou_threshold,
        regression_threshold=req.regression_threshold,
    )

    result_dict = _eval_to_dict(result)
    _save_eval_result(result_dict)
    return result_dict


@evaluation_router.get("/results")
async def list_evaluation_results(limit: int = 50) -> list[dict[str, Any]]:
    """List past evaluation results (most recent first)."""
    all_results = _load_eval_results()
    return list(reversed(all_results[-limit:]))
