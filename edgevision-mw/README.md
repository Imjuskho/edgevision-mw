# EdgeVision-MW Control Plane

AI-powered annotation and data marketplace platform for edge-captured imagery across rural Malawi.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Edge Nodes  │────▶│   Ingestion │────▶│  Annotation │
│  (solar pwr) │     │   Pipeline  │     │   Studio    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  PostgreSQL │     │  AI Models  │
                    │  + pgvector │     │  (YOLO/CLIP)│
                    └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Data       │
                    │  Marketplace│
                    └─────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 16 + pgvector, Redis 7 |
| Storage | MinIO (S3-compatible) |
| Workers | Celery (Redis broker) |
| AI | YOLOv8, MobileSAM, CLIP ViT-B/32 (ONNX Runtime) |
| Frontend | React 18, TypeScript, Vite, Fabric.js v6 |
| DevOps | Docker Compose, GitHub Actions, Prometheus |

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with secure values

# 2. Start services
docker compose up -d

# 3. Run migrations
docker compose exec app alembic upgrade head

# 4. Create admin user
docker compose exec app python -c "
from app.core.database import async_session
from app.auth.service import create_user
import asyncio
asyncio.run(create_user(asyncio.run(async_session().__aenter__()), {
    'email': 'admin@edgevision.mw', 'password': 'admin123',
    'full_name': 'Admin', 'role': 'ADMIN'
}))
"

# 5. Access API docs
open http://localhost:8000/docs
```

## Development

```bash
# Backend (local)
cd edgevision-mw
source .venv/bin/activate
POSTGRES_HOST=localhost uvicorn app.main:app --reload --port 8000

# Frontend (local)
cd frontend
npx vite --host --port 3000

# Run tests (189 tests)
POSTGRES_HOST=localhost python -m pytest tests/ -v

# Lint
ruff check app/
ruff format app/
```

### Running Celery worker (local)

For end-to-end auto-prelabeling, run a Celery worker and beat scheduler locally:

```bash
# From project root
./scripts/run_celery_worker.sh    # starts worker
./scripts/run_celery_beat.sh      # starts beat (optional)
```

The worker requires Redis and Postgres to be reachable (see `docker-compose.yml`).

## API Endpoints

All routes prefixed with `/api/v1`:

| Module | Endpoints | Description |
|--------|-----------|-------------|
| **Auth** | POST `/auth/register`, `/auth/login`, `/auth/api-keys` | Registration, JWT, API keys |
| **Fleet** | POST `/nodes/heartbeat`, GET `/nodes/`, `/nodes/alerts` | Device telemetry, status |
| **Ingestion** | POST `/ingest/batch`, GET `/ingest/queue`, `/ingest/batches` | Batch upload, validation |
| **Annotation** | POST `/jobs/assign`, `/{id}/submit`, `/{id}/review` | Assignment, labeling, QA |
| **Catalog** | GET `/datasets/`, POST `/datasets/build`, `/datasets/quotes` | Search, build, pricing |
| **Compliance** | POST `/consent/record`, `/consent/withdraw`, GET `/consent/verify` | GDPR consent, PII |
| **Billing** | POST `/exports`, GET `/billing/revenue` | Payment, delivery |
| **Studio** | POST `/studio/sessions`, `/studio/annotations` | AI annotation studio |
| **Studio AI** | POST `/studio/ai-assist`, `/studio/prelabel/image` | YOLO/SAM/CLIP inference |
| **Metrics** | GET `/metrics` | Prometheus format |

## AI Features

- **Browser-side AI Assist**: YOLOv8 classifier + MobileSAM via ONNX Runtime WASM
- **Server-side Pre-labeling**: Sliding-window YOLO + NMS for batch pre-annotation
- **CLIP Semantic Dedup**: ViT-B/32 512-dim embeddings for duplicate detection
- **Malawi Taxonomy**: 13 categories, 85 classes, 6 scene-level attributes

## Deployment Modes

The platform runs in two deployment modes controlled by the `INSTALL_TRAINING_DEPS` env var:

| Mode | `INSTALL_TRAINING_DEPS` | Description |
|------|------------------------|-------------|
| **API Server** (`app`) | `false` | FastAPI app serving REST endpoints, inference, and model registry. No ultralytics/torch dependency. |
| **Celery Worker** (`celery_worker`, `celery_beat`) | `true` | Background task execution including auto-labeling with YOLO segmentation models. Full ultralytics stack. |

The API server container avoids the ~1GB ultralytics dependency, keeping image size small. Workers handle all YOLO inference.

### Model Format Detection

Deployed models use auto-detection based on file extension:
- `.onnx` → ONNX Runtime (`ONNXEngine`)
- `.pt` → ultralytics YOLO (`TrainedModelEngine`)
- `.torchscript` → TorchScript (reserved, not yet implemented)

Set `format` field in `DeployedModel` to override auto-detection.

### Orphaned ModelType Values

The original `ModelType` enum included `sign_detection` and `pose_estimation` values that were never deployed. If you see these in your database, remove them:

```sql
DELETE FROM deployed_models WHERE model_type IN ('sign_detection', 'pose_estimation');
```SQL was originally: `SELECT * FROM deployed_models WHERE model_type NOT IN ('road_segmentation','agri_crop_classification','agri_health_classification','object_detection','classification');` -- after verification, clean up with the DELETE above.

## Celery Health

The platform exposes a `GET /health/celery` endpoint that checks liveness via Redis heartbeat keys:

- **Beat**: `heartbeat:celery_beat` — set by Celery beat scheduler
- **Workers**: `heartbeat:worker:*` — set by Celery worker processes  
- **Tasks**: `heartbeat:task:*` — set at end of each periodic task execution

Heartbeats are written with a TTL of `CELERY_TASK_HEARTBEAT_TTL` (default 300s). Stale detection uses 2x TTL.

## Observability

- **Metrics**: `GET /metrics` exposes Prometheus counters for HTTP requests, annotations, uploads, datasets, sessions, and Celery tasks
- **Logging**: Structured JSON logs via `structlog` with correlation IDs (`X-Request-ID`)
- **Sentry**: Error tracking with PII scrubbing — set `SENTRY_DSN` env var to enable

## Testing

```bash
# Full suite
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_studio.py -v

# With coverage
python -m pytest tests/ --cov=app --cov-report=term-missing
```

## License

Proprietary — EdgeVision Data Platforms Ltd.
