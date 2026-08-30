FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY rebob ./rebob

RUN pip install --no-cache-dir ".[hosted]"

ENV REBOB_BACKEND=postgres
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "-m", "rebob.server", "--transport", "http", "--port", "8080", "--host", "0.0.0.0"]
