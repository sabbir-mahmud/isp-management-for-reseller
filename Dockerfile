# Build a runnable image, not a development box.
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libpq for psycopg, curl for the container healthcheck. No compilers: the
# wheels used here are all binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so a code change does not re-resolve the whole tree.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Collect static at build time; the running container needs no write access
# to the image for it. SECRET_KEY is required by settings but is not baked in
# — this value exists only for the duration of this one command.
RUN SECRET_KEY=build-only-not-a-real-key DEBUG=False \
    python manage.py collectstatic --noinput --clear

# Never run as root.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["gunicorn", "isp_management.wsgi:application", "--config", "gunicorn.conf.py"]
