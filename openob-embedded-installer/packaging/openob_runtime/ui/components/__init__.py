# -*- coding: utf-8 -*-
"""
UI Components package.

Reusable UI widgets and dialog windows.
"""

from .widgets import VUCircle, ReceiverBar, LogPanel, IconLoader
from .dialogs import SettingsDialog, CloseDialog, SettingsResult
from .config import (
    ConfigView,
    ConfigController,
    ConfigState,
    ConfigResult,
    TransmissionMode,
    open_config_view
)

# Alias for compatibility
VUMeterCircle = VUCircle

__all__ = [
    'VUCircle',
    'VUMeterCircle',
    'ReceiverBar',
    'LogPanel',
    'IconLoader',
    'SettingsDialog',
    'CloseDialog',
    'SettingsResult',
    'ConfigView',
    'ConfigController',
    'ConfigState',
    'ConfigResult',
    'TransmissionMode',
    'open_config_view',
]