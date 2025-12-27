# OpenOB embedded installer (Windows)

Este subproyecto genera un instalador **self-contained** para Windows que incluye:

- **Python embebido (python.org embeddable zip)** dentro del directorio de instalación.
- Dependencias Python necesarias (por ejemplo `redis`, `pystray`, `pillow`).
- El paquete `openob` instalado desde `../openob`.
- La **UI (Tkinter)** desde `../ui` (se copia dentro del directorio de instalación).
- (Opcional) Binarios de **Redis for Windows** copiando desde `../redis-server`.

No intenta “inventar” dependencias: para audio/GStreamer, se mantiene el mismo modelo del workspace: **GStreamer instalado en el sistema** (o ajustado vía `config/gstreamer.env`).

## Uso rápido

Desde la raíz del repo:

- Construir runtime embebido (descarga Python, instala pip+deps, instala OpenOB, copia Redis):

  `powershell -ExecutionPolicy Bypass -File .\openob-embedded-installer\scripts\build_all.ps1`

- Construir instalador (requiere Inno Setup 6):

  `powershell -ExecutionPolicy Bypass -File .\openob-embedded-installer\scripts\50_build_installer.ps1`

## Estructura

- `scripts/`: pasos reproducibles (PowerShell).
- `packaging/openob_runtime/`: “payload” que se empaqueta en el instalador.
- `installer/inno/`: plantilla de Inno Setup (`.iss`).
- `manual/`: guía de build/validación.

## Accesos directos

- El instalador crea un acceso directo en el **Escritorio** llamado "OpenOB UI" que lanza la UI usando `{app}\python\pythonw.exe "{app}\ui\app.py` (sin ventana de consola).
