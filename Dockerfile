# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder
WORKDIR /build

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runner

# Install OpenCV and runtime C dependencies and curl for healthcheck
RUN apt-get update && apt-get install --no-install-recommends -y \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10002 aiuser \
    && useradd --uid 10002 --gid aiuser --create-home aiuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY api ./api
COPY models ./models
COPY services ./services
COPY utils ./utils
COPY Scripts ./Scripts
COPY config.py ./config.py
COPY main.py ./main.py

RUN chown -R aiuser:aiuser /app

USER aiuser
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["curl", "-f", "http://127.0.0.1:8001/"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
