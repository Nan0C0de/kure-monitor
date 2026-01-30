"""
Centralized Prometheus metrics registry for Kure Monitor.

All metric objects are defined here. Other modules import and
increment/observe/set these objects at instrumentation points.
"""
from prometheus_client import Counter, Gauge, Summary

# Pod Failure Metrics
POD_FAILURES_TOTAL = Counter(
    "kure_pod_failures_total",
    "Total number of pod failures reported to the backend",
    ["namespace", "reason"],
)

# LLM Request Metrics
LLM_REQUESTS_TOTAL = Counter(
    "kure_llm_requests_total",
    "Total LLM API requests by provider and outcome",
    ["provider", "status"],
)

LLM_REQUEST_DURATION_SECONDS = Summary(
    "kure_llm_request_duration_seconds",
    "Duration of LLM API requests in seconds",
    ["provider"],
)

# Security Finding Metrics
SECURITY_FINDINGS_TOTAL = Counter(
    "kure_security_findings_total",
    "Total security findings reported to the backend",
    ["severity"],
)

SECURITY_SCAN_DURATION_SECONDS = Gauge(
    "kure_security_scan_duration_seconds",
    "Duration of the last security scan in seconds",
)

# Backend Health Metrics
WEBSOCKET_CONNECTIONS_ACTIVE = Gauge(
    "kure_websocket_connections_active",
    "Number of currently active WebSocket connections",
)

DATABASE_QUERIES_TOTAL = Counter(
    "kure_database_queries_total",
    "Total number of database queries executed",
)
