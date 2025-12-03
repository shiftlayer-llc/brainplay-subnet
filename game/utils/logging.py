# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2025 ShiftLayer

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import os
import json
import time
import logging
import functools
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from contextvars import ContextVar

# Context variable for request ID tracking
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

EVENTS_LEVEL_NUM = 38
DEFAULT_LOG_BACKUP_COUNT = 10
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_LOG_ROTATION_WHEN = 'midnight'  # Rotate at midnight
DEFAULT_LOG_ROTATION_INTERVAL = 1  # Daily rotation


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add request ID if available
        request_id = request_id_var.get()
        if request_id:
            log_data['request_id'] = request_id
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data, default=str)


class RequestIDFilter(logging.Filter):
    """Filter to add request ID to log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add request ID to log record if available."""
        request_id = request_id_var.get()
        if request_id:
            record.request_id = request_id
        return True


class PerformanceLogger:
    """Performance logging decorator and context manager."""
    
    @staticmethod
    def log_performance(logger: Optional[logging.Logger] = None, log_level: int = logging.INFO):
        """
        Decorator to log function execution time.
        
        Args:
            logger: Logger instance to use. If None, uses default logger.
            log_level: Log level to use for performance logs.
        """
        def decorator(func):
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                func_logger = logger or logging.getLogger(func.__module__)
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    func_logger.log(
                        log_level,
                        f"Function {func.__name__} executed in {execution_time:.4f}s",
                        extra={'function': func.__name__, 'execution_time': execution_time}
                    )
                    return result
                except Exception as e:
                    execution_time = time.time() - start_time
                    func_logger.log(
                        logging.ERROR,
                        f"Function {func.__name__} failed after {execution_time:.4f}s: {str(e)}",
                        extra={'function': func.__name__, 'execution_time': execution_time, 'error': str(e)},
                        exc_info=True
                    )
                    raise
            
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                func_logger = logger or logging.getLogger(func.__module__)
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    func_logger.log(
                        log_level,
                        f"Async function {func.__name__} executed in {execution_time:.4f}s",
                        extra={'function': func.__name__, 'execution_time': execution_time}
                    )
                    return result
                except Exception as e:
                    execution_time = time.time() - start_time
                    func_logger.log(
                        logging.ERROR,
                        f"Async function {func.__name__} failed after {execution_time:.4f}s: {str(e)}",
                        extra={'function': func.__name__, 'execution_time': execution_time, 'error': str(e)},
                        exc_info=True
                    )
                    raise
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        return decorator
    
    @staticmethod
    def context_manager(operation_name: str, logger: Optional[logging.Logger] = None, log_level: int = logging.INFO):
        """
        Context manager for performance logging.
        
        Args:
            operation_name: Name of the operation being timed.
            logger: Logger instance to use. If None, uses default logger.
            log_level: Log level to use for performance logs.
        """
        class PerformanceContext:
            def __init__(self, name: str, logger_instance: Optional[logging.Logger], level: int):
                self.name = name
                self.logger = logger_instance or logging.getLogger(__name__)
                self.level = level
                self.start_time = None
            
            def __enter__(self):
                self.start_time = time.time()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                execution_time = time.time() - self.start_time
                if exc_type is None:
                    self.logger.log(
                        self.level,
                        f"Operation '{self.name}' completed in {execution_time:.4f}s",
                        extra={'operation': self.name, 'execution_time': execution_time}
                    )
                else:
                    self.logger.log(
                        logging.ERROR,
                        f"Operation '{self.name}' failed after {execution_time:.4f}s: {str(exc_val)}",
                        extra={'operation': self.name, 'execution_time': execution_time, 'error': str(exc_val)},
                        exc_info=True
                    )
                return False
        
        return PerformanceContext(operation_name, logger, log_level)


def set_request_id(request_id: str):
    """Set request ID for the current context."""
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """Get current request ID."""
    return request_id_var.get()


def clear_request_id():
    """Clear request ID from current context."""
    request_id_var.set(None)


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    use_json: bool = False,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
    rotation_when: str = DEFAULT_LOG_ROTATION_WHEN,
    rotation_interval: int = DEFAULT_LOG_ROTATION_INTERVAL,
    use_timed_rotation: bool = False,
) -> logging.Logger:
    """
    Setup a logger with configurable options.
    
    Args:
        name: Logger name
        log_file: Path to log file (optional)
        level: Logging level
        use_json: Use JSON formatting if True
        max_bytes: Maximum bytes before rotation (for RotatingFileHandler)
        backup_count: Number of backup files to keep
        rotation_when: When to rotate ('S', 'M', 'H', 'D', 'W0'-'W6', 'midnight')
        rotation_interval: Rotation interval (for TimedRotatingFileHandler)
        use_timed_rotation: Use time-based rotation instead of size-based
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create formatter
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | [%(name)s] | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RequestIDFilter())
    logger.addHandler(console_handler)
    
    # Add file handler if log_file is provided
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        if use_timed_rotation:
            file_handler = TimedRotatingFileHandler(
                log_file,
                when=rotation_when,
                interval=rotation_interval,
                backupCount=backup_count,
                encoding='utf-8',
            )
        else:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8',
            )
        
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RequestIDFilter())
        logger.addHandler(file_handler)
    
    return logger


def setup_events_logger(
    full_path: str,
    events_retention_size: int,
    use_json: bool = False,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
    use_timed_rotation: bool = False,
    rotation_when: str = DEFAULT_LOG_ROTATION_WHEN,
    rotation_interval: int = DEFAULT_LOG_ROTATION_INTERVAL,
) -> logging.Logger:
    """
    Setup the events logger with improved rotation options.
    
    Args:
        full_path: Directory path for log files
        events_retention_size: Maximum size before rotation (for size-based rotation)
        use_json: Use JSON formatting if True
        backup_count: Number of backup files to keep
        use_timed_rotation: Use time-based rotation instead of size-based
        rotation_when: When to rotate ('S', 'M', 'H', 'D', 'W0'-'W6', 'midnight')
        rotation_interval: Rotation interval (for TimedRotatingFileHandler)
    
    Returns:
        Configured events logger
    """
    logging.addLevelName(EVENTS_LEVEL_NUM, "EVENT")

    logger = logging.getLogger("event")
    logger.setLevel(EVENTS_LEVEL_NUM)

    def event(self, message, *args, **kws):
        if self.isEnabledFor(EVENTS_LEVEL_NUM):
            self._log(EVENTS_LEVEL_NUM, message, args, **kws)

    logging.Logger.event = event

    # Create formatter
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    log_file_path = os.path.join(full_path, "events.log")
    
    # Choose rotation handler based on configuration
    if use_timed_rotation:
        file_handler = TimedRotatingFileHandler(
            log_file_path,
            when=rotation_when,
            interval=rotation_interval,
            backupCount=backup_count,
            encoding='utf-8',
        )
    else:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=events_retention_size,
            backupCount=backup_count,
            encoding='utf-8',
        )
    
    file_handler.setFormatter(formatter)
    file_handler.setLevel(EVENTS_LEVEL_NUM)
    file_handler.addFilter(RequestIDFilter())
    logger.addHandler(file_handler)

    return logger


# Import asyncio for async function detection
import asyncio
