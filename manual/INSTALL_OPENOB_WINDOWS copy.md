# Instalación rápida de OpenOB en Windows

Comandos mínimos y reproducibles para este workspace. Ejecuta los pasos desde la raíz del proyecto (por ejemplo: `C:\Users\vamanuel\Documents\openob_windows`).

## Requisitos previos

- Windows + Python 3.12+ x64.
- GStreamer runtime MSVC x86_64 instalado (ruta típica: `C:\Program Files\gstreamer\1.0\msvc_x86_64`).
- Redis instalado como servicio Windows y en ejecución (o usar los scripts del repo).

## 1) Crear y activar entorno virtual

En PowerShell (una vez por usuario, si hace falta):

    Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

Crear el venv y activarlo:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

## 2) Instalar dependencias y OpenOB

Actualizar herramientas:

    .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

Instalar dependencias:

    .\.venv\Scripts\python.exe -m pip install redis pystray pillow

Instalar OpenOB desde el subproyecto `openob`:

    cd .\openob
    ..\.venv\Scripts\python.exe -m pip install .
    cd ..

## 3) Exponer bindings de GStreamer al venv

Si GStreamer está instalado en la ruta por defecto, crea un `.pth` en el `site-packages` del venv:

    Set-Content -Encoding ASCII -Path .\.venv\Lib\site-packages\gstreamer.pth -Value "C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\site-packages"

En la sesión PowerShell donde lances OpenOB/UI añade:

    $env:PATH += ';C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'
    $env:GI_TYPELIB_PATH = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'

Comprobación:

    .\.venv\Scripts\python.exe -c "import gi; from gi.repository import Gst; print('GStreamer OK')"

## 4) Redis como servicio

Ver estado:

    Get-Service -Name Redis

Arrancar (si existe y está detenido):

    Start-Service -Name Redis

Instalar como servicio (requiere PowerShell elevado), si aún no existe:

    .\scripts\install_redis_service.ps1

Comprobar que escucha en localhost:

    Test-NetConnection -ComputerName 127.0.0.1 -Port 6379

## 5) Lanzar OpenOB

Recomendado: usar el helper (configura entorno y arranca OpenOB desde el venv). Ejecuta desde la raíz del repo:

    .\scripts\start_openob.ps1 -OpenobArgs '-v 127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'

Notas:
- El helper intenta `openob.exe` y, si no existe, usa `python -m openob`.
- Si lo haces manualmente, en Windows el entrypoint suele ser `openob.exe` (no `openob` sin extensión).

## 6) Lanzar la UI (opcional)

Desde la raíz del repo:

    .\.venv\Scripts\python.exe .\ui\app.py

O usando el acceso directo:

    .\scripts\run_ui.bat
