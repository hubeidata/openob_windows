@echo off
REM Ajusta rutas si tu repo está en otro sitio
cd /d "C:\Users\vamanuel\Documents\openob_windows"

REM Preferir GStreamer empaquetado en runtime si existe, sino usar la instalación del sistema
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

REM Ejecutar la UI con la Python del venv
call ".\.venv\Scripts\python.exe" ".\ui\main.py"

pause