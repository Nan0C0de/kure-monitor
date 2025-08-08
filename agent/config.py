import os

class Config:
    def __init__(self):
        self.backend_url = os.getenv('KURE_BACKEND_URL', 'http://kure-backend:8000')
        self.check_interval = int(os.getenv('KURE_CHECK_INTERVAL', '5'))  # seconds
        self.log_level = os.getenv('KURE_LOG_LEVEL', 'INFO')
