import os

class Config:
    def __init__(self):
        # Read backend URL from environment variable, with fallback to correct service name
        self.backend_url = os.getenv('BACKEND_URL', 'http://kure-monitor-backend:8000')
        self.check_interval = int(os.getenv('KURE_CHECK_INTERVAL', '5'))  # seconds
        self.log_level = os.getenv('KURE_LOG_LEVEL', 'INFO')
        # Cluster metrics collection (can be disabled via Helm values)
        self.cluster_metrics_enabled = os.getenv('CLUSTER_METRICS_ENABLED', 'true').lower() == 'true'
