import os

class Config:
    def __init__(self):
        # Fixed backend URL for security - users cannot modify this
        self.backend_url = 'http://kure-backend:8000'
        self.check_interval = int(os.getenv('KURE_CHECK_INTERVAL', '5'))  # seconds
        self.log_level = os.getenv('KURE_LOG_LEVEL', 'INFO')
