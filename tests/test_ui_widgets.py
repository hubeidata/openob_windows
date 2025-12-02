import pytest
import tkinter as tk
from ui.main import OpenOBGUI, DEFAULT_OPENOB_ARGS


def test_ui_widgets_create_and_defaults():
    # Create UI without starting mainloop
    app = OpenOBGUI()
    try:
        assert hasattr(app, 'args_var')
        assert hasattr(app, 'local_vu_canvas')
        assert hasattr(app, 'remote_vu_canvas')
        assert hasattr(app, 'btn_toggle_logs')
        assert hasattr(app, 'redis_card')
        assert hasattr(app, 'openob_card')
        # default args var set
        assert app.args_var.get() == DEFAULT_OPENOB_ARGS
    finally:
        # Destroy the Tk instance so tests don't leak windows
        try:
            app.destroy()
        except Exception:
            pass
