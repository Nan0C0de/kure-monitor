import logging
import os

logger = logging.getLogger(__name__)


class Config:
    def __init__(self):
        # Read backend URL from environment variable, with fallback to correct service name
        self.backend_url = os.getenv('BACKEND_URL', 'http://kure-monitor-backend:8000')
        self.check_interval = int(os.getenv('KURE_CHECK_INTERVAL', '5'))  # seconds
        self.log_level = os.getenv('KURE_LOG_LEVEL', 'INFO')
        # Grace period before reporting Pending pods as failed (default 2 minutes)
        self.pending_grace_period = int(os.getenv('PENDING_GRACE_PERIOD', '120'))  # seconds
        # Failure log capture (CrashLoopBackOff / OOMKilled only). Gzip + base64 encoded.
        self.failure_logs_enabled = os.getenv('FAILURE_LOGS_ENABLED', 'true').lower() == 'true'
        self.failure_logs_max_lines = int(os.getenv('FAILURE_LOGS_MAX_LINES', '1000'))
        # Service token for authenticating ingest requests to the backend.
        # When missing we stay up but every backend call will be rejected with 401 —
        # this is a degraded mode, not a crash condition.
        self.service_token = os.getenv('SERVICE_TOKEN')
        if not self.service_token:
            logger.error(
                "SERVICE_TOKEN environment variable is not set. "
                "Agent will continue running in degraded mode; backend will reject all requests with 401."
            )
