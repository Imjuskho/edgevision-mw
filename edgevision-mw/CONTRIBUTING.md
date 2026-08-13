# Contributing to EdgeVision-MW

## Setup

```bash
# Clone
git clone <repo-url>
cd edgevision-mw

# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Frontend
cd frontend && npm install && cd ..
```

## Code Style

### Python
- **Formatter**: `ruff format app/`
- **Linter**: `ruff check app/ --fix`
- **Type hints**: Required on all function signatures
- **Async**: All DB operations use `AsyncSession`
- **Imports**: Sorted by `ruff` (isort-compatible)

### TypeScript
- **Formatter**: Prettier (if configured)
- **Linter**: `npx tsc --noEmit`
- **Components**: Functional components with hooks
- **Styling**: CSS variables from `studio.css` design system

## Testing

```bash
# Run all tests
POSTGRES_HOST=localhost python -m pytest tests/ -v

# Run specific test
POSTGRES_HOST=localhost python -m pytest tests/test_studio.py::test_create_session -v

# Check coverage
python -m pytest tests/ --cov=app --cov-report=term-missing
```

### Writing Tests

- Use `test_client` fixture for HTTP tests
- Use `db_session` fixture for direct DB tests
- Use `jwt_token_factory` for auth: `token = jwt_token_factory(role="ADMIN")`
- Prefix test files with `test_` and group by feature
- Async tests use `@pytest.mark.asyncio`

## Pull Requests

1. Create feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass: `python -m pytest tests/ -v`
4. Run linter: `ruff check app/`
5. Update documentation if adding API endpoints
6. Submit PR with clear description

## Project Structure

```
app/
├── api/           # FastAPI route handlers
├── auth/          # Authentication (JWT, API keys)
├── core/          # Config, DB, security, logging
├── models/        # SQLAlchemy models
├── schemas/       # Pydantic request/response schemas
├── services/      # Business logic (async)
└── workers/       # Celery background tasks

frontend/src/
├── components/    # Reusable UI components
├── hooks/         # Custom React hooks
├── pages/         # Page-level components
├── services/      # API client
└── styles/        # CSS design system

tests/
├── test_*.py      # Test modules
└── conftest.py    # Shared fixtures
```

## Commit Messages

Use conventional commits:
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation
- `test:` adding tests
- `refactor:` code restructuring
- `chore:` tooling, config

Example: `feat: add CLIP embedding endpoint for semantic dedup`
