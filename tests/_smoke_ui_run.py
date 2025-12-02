from ui.main import OpenOBGUI, DEFAULT_OPENOB_ARGS

def run_smoke():
    app = OpenOBGUI()
    try:
        assert hasattr(app, 'args_var')
        assert hasattr(app, 'local_vu_canvas')
        assert hasattr(app, 'remote_vu_canvas')
        assert hasattr(app, 'btn_toggle_logs')
        assert app.args_var.get() == DEFAULT_OPENOB_ARGS
        print('SMOKE OK')
    finally:
        try:
            app.destroy()
        except Exception:
            pass

if __name__ == '__main__':
    run_smoke()
