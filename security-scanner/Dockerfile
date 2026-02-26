# Build stage - install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

RUN apt-get update && apt-get upgrade -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN groupadd -r kure && useradd -r -g kure -d /app -s /sbin/nologin kure

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=kure:kure . .

ENV PATH="/opt/venv/bin:$PATH"
USER kure

CMD ["python", "main.py"]
