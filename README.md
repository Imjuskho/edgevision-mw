# Edge Vision Data Platform

A distributed edge-computing data platform deployed across rural Malawi: a fleet of
solar-powered edge devices capture road, agricultural, wildlife, documentary, and
biometric imagery, which then flows through ingestion, human-in-the-loop annotation,
QA, dataset assembly, and finally to a data marketplace.

This repository is the workspace root. The main product lives in
[`edgevision-mw/`](edgevision-mw/).

## Repository layout

| Path | Description |
|------|-------------|
| [`edgevision-mw/`](edgevision-mw/) | Control plane — FastAPI backend, React frontend, Celery workers, Alembic migrations, tests |
| [`edgevision-mw/docs/`](edgevision-mw/docs/) | Deployment, field, annotator, and buyer guides |
| [`scripts/`](edgevision-mw/scripts/activation/) | Production activation scripts (node registration, batch processing, reporting) |
| `PHASE*.md`, `PLAN.md`, `PROJECT_STATUS_REPORT.md`, `AUDIT_UX.md` | Development phase plans, status, and audit docs |
| [`clip_dedup/`](clip_dedup/) | CLIP-based image deduplication tooling |

## Getting started

See [`edgevision-mw/README.md`](edgevision-mw/README.md) for the full project
documentation, architecture, tech stack, and quick-start commands.

```bash
cd edgevision-mw
cp .env.example .env   # fill in secure values
docker compose up -d
docker compose exec app alembic upgrade head
docker compose exec app pytest tests/ -v
```

## Support / Donate

This project is built and maintained in Malawi. If it helps you and you would like
to support the team behind it, any contribution is hugely appreciated.

**EFT / Direct bank transfer**

| Field | Details |
|-------|---------|
| Bank | National Bank of Malawi |
| Account name | PHANGA CREATIVES |
| Account number | 1005100832 |
| Transfer type | EFT (Electronic Funds Transfer) |

More donation options (GitHub Sponsors, PayPal, etc.) coming soon.

## Note on Git LFS

Large local artifacts (Python `wheelhouse/`, local image datasets, and the Celery
beat schedule DB) are stored via [Git LFS](https://git-lfs.com). Pull the repo with
`git lfs pull` after cloning if you need these files.