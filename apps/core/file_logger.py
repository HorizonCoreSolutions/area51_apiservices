import logging
import os
from logging.handlers import RotatingFileHandler

class SimpleLogger:
    def __init__(
        self,
        name: str = 'app',
        log_file: str = 'app.log',
        level: int = logging.DEBUG,
        max_bytes: int = 5 * 1024 * 1024,  # 5 MB
        backup_count: int = 3,
        console: bool = True
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Avoid adding handlers multiple times
        if not self.logger.handlers:

            formatter = logging.Formatter(
                '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # Ensure the directory exists
            os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            if console:
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)

    def get_logger(self):
        return self.logger
