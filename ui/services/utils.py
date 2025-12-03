# -*- coding: utf-8 -*-
"""
utils.py - Utility functions and helpers.

Design decisions:
- Centralized logging configuration
- Path utilities
- Audio level conversion utilities
- Common constants
"""

import logging
import math
import random
import time
from pathlib import Path
from typing import Tuple, Optional


# Module-level logger cache
_loggers: dict = {}
_log_file: Optional[Path] = None


def configure_logging(log_file: Path, level: int = logging.INFO) -> None:
    """
    Configure global logging for the application.
    
    Args:
        log_file: Path to log file
        level: Logging level
    """
    global _log_file
    _log_file = log_file
    
    # Ensure directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger for openob.ui namespace
    root_logger = logging.getLogger('openob.ui')
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add file handler
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setFormatter(
        logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
    )
    root_logger.addHandler(handler)
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
    """
    if name not in _loggers:
        # Normalize name to openob.ui namespace
        if not name.startswith('openob.ui'):
            name = f'openob.ui.{name.split(".")[-1]}'
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]


def setup_logging(log_file: Path, logger_name: str = 'openob.ui') -> logging.Logger:
    """
    Setup logging configuration.
    
    Args:
        log_file: Path to log file
        logger_name: Logger name
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding='utf-8')
        handler.setFormatter(
            logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        )
        logger.addHandler(handler)
        logger.propagate = False
    
    return logger


def db_to_normalized(db_value: float, min_db: float = -65.0, gamma: float = 0.7) -> float:
    """
    Convert dB value to normalized 0..1 range.
    
    Uses gamma curve for better resolution at high levels.
    
    Args:
        db_value: Audio level in dB (0 = max, negative = quieter)
        min_db: Minimum dB value (maps to 0.0)
        gamma: Gamma curve factor (< 1 expands high values)
        
    Returns:
        Normalized value between 0.0 and 1.0
    """
    if db_value is None:
        return 0.0
    
    try:
        db = float(db_value)
        db = max(min_db, min(0.0, db))
        
        # Linear normalization
        linear = (db - min_db) / (0.0 - min_db)
        
        # Apply gamma curve
        curved = math.pow(linear, gamma)
        
        return curved
    except (ValueError, TypeError):
        return 0.0


def apply_vu_jitter(
    left: float, 
    right: float, 
    avg_level: float
) -> Tuple[float, float, float]:
    """
    Apply jitter to VU values based on level.
    
    Higher levels get more jitter for visible oscillation.
    
    Args:
        left: Left channel normalized value
        right: Right channel normalized value
        avg_level: Average level for jitter calculation
        
    Returns:
        Tuple of (left, right, smoothing_factor)
    """
    if avg_level > 0.6:
        # High level: maximum responsiveness, large jitter
        smooth = 0.05
        jitter_l = random.uniform(-0.15, 0.15)
        jitter_r = random.uniform(-0.15, 0.15)
    elif avg_level > 0.35:
        # Medium level: low smoothing, moderate jitter
        smooth = 0.2
        jitter_l = random.uniform(-0.08, 0.08)
        jitter_r = random.uniform(-0.08, 0.08)
    elif avg_level > 0.15:
        # Low-medium: some jitter
        smooth = 0.4
        jitter_l = random.uniform(-0.04, 0.04)
        jitter_r = random.uniform(-0.04, 0.04)
    else:
        # Very low: stability
        smooth = 0.6
        jitter_l = 0.0
        jitter_r = 0.0
    
    left_out = max(0.0, min(1.0, left + jitter_l))
    right_out = max(0.0, min(1.0, right + jitter_r))
    
    return left_out, right_out, smooth


def smooth_value(old_value: float, new_value: float, smooth_factor: float) -> float:
    """
    Apply exponential smoothing to a value.
    
    Args:
        old_value: Previous value
        new_value: New target value
        smooth_factor: Smoothing factor (0 = instant, 1 = no change)
        
    Returns:
        Smoothed value
    """
    return smooth_factor * old_value + (1 - smooth_factor) * new_value


def get_refresh_rate_ms(avg_level: float) -> int:
    """
    Get animation refresh rate based on audio level.
    
    Higher levels = faster refresh for more visible movement.
    
    Args:
        avg_level: Average audio level (0..1)
        
    Returns:
        Refresh interval in milliseconds
    """
    if avg_level > 0.7:
        return 40   # Fast at high levels
    elif avg_level > 0.4:
        return 60   # Medium
    else:
        return 80   # Normal at low levels


def simulate_vu_level(seed_offset: float = 0.0, amplitude: float = 0.85) -> float:
    """
    Generate simulated VU level for testing/demo.
    
    Args:
        seed_offset: Time offset for variation
        amplitude: Maximum amplitude
        
    Returns:
        Simulated level between 0 and 1
    """
    t = time.time()
    base = abs(math.sin(t * 2.5 + seed_offset))
    noise = random.random() * 0.15
    return base * amplitude + noise


def format_timestamp(format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    Get formatted current timestamp.
    
    Args:
        format_str: strftime format string
        
    Returns:
        Formatted timestamp string
    """
    return time.strftime(format_str)


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """
    Clamp value to range.
    
    Args:
        value: Input value
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        Clamped value
    """
    return max(min_val, min(max_val, value))
