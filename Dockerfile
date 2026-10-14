FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 watcher \
    && mkdir -p /data \
    && chown 10001:10001 /data

USER watcher
VOLUME ["/data"]

CMD ["bupt-activity", "--watch", "--state", "/data/seen.json"]
