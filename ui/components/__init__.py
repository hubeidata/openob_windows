# -*- coding: utf-8 -*-
"""
UI Components package.

Reusable UI widgets and dialog windows.
"""

from .widgets import VUCircle, ReceiverBar, LogPanel, IconLoader
from .dialogs import SettingsDialog, CloseDialog, SettingsResult

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
]