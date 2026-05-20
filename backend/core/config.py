"""Application configuration values loaded from environment variables."""

import os


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# Feature flag controlling whether previous-container failure logs sent
# by the agent are persisted on CrashLoopBackOff / OOMKilled events.
FAILURE_LOGS_ENABLED: bool = _env_bool("FAILURE_LOGS_ENABLED", "true")

# Upper bound on lines captured per container (informational; the agent
# enforces the true cap).  Kept here so future log-scoped code can share
# a single source of truth.
FAILURE_LOGS_MAX_LINES: int = int(os.getenv("FAILURE_LOGS_MAX_LINES", "1000"))

# Defensive hard cap on the raw (pre-gzip) byte size stored per log entry.
# If the agent exceeds this we mark the row as truncated but still accept it.
FAILURE_LOGS_MAX_BYTES: int = 256 * 1024

# Maximum number of recent log lines included in the log-aware LLM prompt.
LLM_LOGS_TAIL_LINES: int = int(os.getenv("LLM_LOGS_TAIL_LINES", "200"))

# Maximum YAML manifest size included in the log-aware LLM prompt (bytes).
LLM_MANIFEST_MAX_BYTES: int = int(os.getenv("LLM_MANIFEST_MAX_BYTES", str(8 * 1024)))

# Feature toggles. Surfaced to the frontend via /api/config so each tab
# can be hidden when the operator disables that feature in Helm values.
# Default ON so existing deployments behave identically.
FEATURE_POD_MONITORING: bool = _env_bool("FEATURE_POD_MONITORING", "true")
FEATURE_SECURITY_SCAN: bool = _env_bool("FEATURE_SECURITY_SCAN", "true")
FEATURE_DIAGRAM: bool = _env_bool("FEATURE_DIAGRAM", "true")
FEATURE_AI_ADVICE: bool = _env_bool("FEATURE_AI_ADVICE", "true")
