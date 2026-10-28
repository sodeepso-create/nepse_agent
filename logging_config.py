import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import settings


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    # Set log level from settings (defaults to INFO)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    
    # Format: Timestamp [Level] LoggerName: Message
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Ensure the log directory exists
    Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    
    # --- ROTATING FILE HANDLER ---
    # Max size: 5MB per file. Keeps 3 backup files (bot.log, bot.log.1, bot.log.2).
    fh = RotatingFileHandler(
        settings.LOG_FILE, 
        maxBytes=5 * 1024 * 1024, 
        backupCount=3, 
        encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console output (so you can see it in the terminal)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    
    return logger