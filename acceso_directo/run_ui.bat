@echo off
REM Ajusta rutas si tu repo está en otro sitio
cd /d "C:\Users\vamanuel\Documents\openob_windows"

REM Opcional: exponer GStreamer al entorno de la sesión
set "PATH=%PATH%;C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
set "GI_TYPELIB_PATH=C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0"

REM Ejecutar la UI con la Python del venv
call ".\.venv\Scripts\python.exe" ".\ui\main.py"

pause