# Build stage - install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip 'setuptools>=78.1.1' 'wheel>=0.46.2' 'jaraco.context>=6.1.0' && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

RUN apt-get update && apt-get upgrade -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    rm -rf /usr/local/lib/python3.11/site-packages/setuptools* \
           /usr/local/lib/python3.11/site-packages/pkg_resources* \
           /usr/local/lib/python3.11/site-packages/wheel* \
           /usr/local/lib/python3.11/site-packages/pip*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd -r kure && useradd -r -g kure -d /app -s /sbin/nologin kure

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=kure:kure . .

ENV PATH="/opt/venv/bin:$PATH"
USER kure

CMD ["python", "main.py"]
