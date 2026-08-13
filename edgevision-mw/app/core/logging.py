import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

import structlog

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def _add_request_id(logger, method_name, event_dict):
    event_dict["request_id"] = request_id_var.get()
    return event_dict


def _add_timestamp(logger, method_name, event_dict):
    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def setup_logging() -> None:
    import os
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            _add_request_id,
            _add_timestamp,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Quiet noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str):
    return structlog.get_logger(name)


def trace(logger, name: str, trace_id: str, **extra):
    """Log a trace event with consistent structure.

    Usage:
        trace(logger, "endpoint_start", trace_id=trace_id, endpoint="/jobs/assign")
        trace(logger, "db_write_success", trace_id=trace_id, table="annotations", row_id=str(id))
    """
    logger.info(name, trace_id=trace_id, **extra)
