# ---- Stage 1: Builder ----
FROM python:3.12-slim AS builder

ARG INSTALL_TRAINING_DEPS=false

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80-retries

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY wheelhouse /wheelhouse
COPY requirements-training.txt .
RUN if [ "$INSTALL_TRAINING_DEPS" = "true" ]; then \
        pip install --no-cache-dir --prefix=/install --no-index --find-links=/wheelhouse -r requirements-training.txt; \
    fi

# ---- Stage 2: Runtime ----
FROM python:3.12-slim AS runtime

ARG INSTALL_TRAINING_DEPS=false
ENV INSTALL_TRAINING_DEPS=${INSTALL_TRAINING_DEPS}

RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\nAcquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80-retries

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgl1 \
    libgl1-mesa-dri \
    curl \
    postgresql-client \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /code -s /sbin/nologin appuser

WORKDIR /code

COPY --from=builder /install /usr/local
COPY wheelhouse /wheelhouse
COPY requirements-training.txt .
RUN if [ "$INSTALL_TRAINING_DEPS" = "true" ]; then \
        pip install --no-cache-dir --no-index --find-links=/wheelhouse -r requirements-training.txt; \
    fi
COPY . .

RUN chmod +x /code/entrypoint.sh && chown -R appuser:appuser /code

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
