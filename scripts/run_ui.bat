@echo off
REM run_ui.bat - launches the Tkinter UI with pythonw (no console)
REM Place this in the scripts\ folder; it will change directory to the repo root and run pythonw from the venv.

:: Resolve repo root (one level up from this script)
pushd %~dp0\..

:: Ensure we run from repo root
cd /d "%~dp0\.."

:: Prefer bundled GStreamer (if present) otherwise fall back to system install
set "BUNDLED_GST=%~dp0\..\openob_runtime\gstreamer"
if exist "%BUNDLED_GST%\msvc_x86_64\bin\gst-launch-1.0.exe" (
    set "PATH=%BUNDLED_GST%\msvc_x86_64\bin;%PATH%"
    set "GI_TYPELIB_PATH=%BUNDLED_GST%\msvc_x86_64\lib\girepository-1.0"
) else if exist "%BUNDLED_GST%\bin\gst-launch-1.0.exe" (
    set "PATH=%BUNDLED_GST%\bin;%PATH%"
    set "GI_TYPELIB_PATH=%BUNDLED_GST%\lib\girepository-1.0"
) else (
    set "PATH=%PATH%;C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
    set "GI_TYPELIB_PATH=C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0"
)

:: Use pythonw.exe to avoid showing a console window
:: Adjust path if your venv is elsewhere
set "PYTHONW=%~dp0\..\.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
    echo pythonw not found at %PYTHONW%. Trying system pythonw... 
    set "PYTHONW=pythonw.exe"
)
"%PYTHONW%" "%~dp0\..\ui\app.py"

:: return to previous directory
popd
exit /b 0
