from __future__ import annotations

from app.core.config import settings


def init_sentry() -> None:
    if not settings.SENTRY_DSN:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    def _before_send(event: dict, hint: dict) -> dict | None:
        if "request" in event:
            request = event["request"]
            headers = request.get("headers", {})
            sanitized = {}
            for k, v in headers.items():
                low_k = k.lower()
                if any(
                    secret in low_k
                    for secret in ("authorization", "cookie", "x-api-key", "x-node-signature", "x-node-public-key")
                ):
                    sanitized[k] = "[FILTERED]"
                else:
                    sanitized[k] = v
            request["headers"] = sanitized

            if "data" in request and isinstance(request["data"], str):
                try:
                    import json
                    parsed = json.loads(request["data"])
                    for field in ("password", "signature_bytes", "api_key"):
                        if field in parsed:
                            parsed[field] = "[FILTERED]"
                    request["data"] = json.dumps(parsed)
                except Exception:
                    request["data"] = "[FILTERED]"

        return event

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT,
        release=settings.VERSION,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.0,
        before_send=_before_send,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
    )
