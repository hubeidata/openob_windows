# Build del instalador OpenOB (Windows)

Estos pasos generan un instalador basado en **Python embebido** (runtime controlado) y el paquete `openob` de este repo.

## Requisitos

- Windows x64.
- PowerShell 5.1+.
- Acceso a internet (para descargar Python embeddable y get-pip).
- (Para construir el .exe instalador) Inno Setup 6 (`ISCC.exe`).

## 1) Construir el runtime embebido

Desde la raíz del repo:

- `powershell -ExecutionPolicy Bypass -File .\openob-embedded-installer\scripts\build_all.ps1`

Esto hace:

- Descarga y extrae Python embebido en `openob-embedded-installer/packaging/openob_runtime/python/`.
- **Incluye Tkinter** (Tcl/Tk + `tkinter`) dentro del runtime embebido descargando el instalador oficial de Python y copiando los archivos necesarios.
- **Incluye PyGObject (`gi`)** dentro del runtime embebido descargando un `GTK3_Gvsbuild` compatible con la versión de Python del runtime (recomendado: **Python 3.14 x64 — use `cp314`**).
- Habilita `site-packages` en el embeddable (`*._pth` + `import site`).
- Opcional: puedes incluir una distribución de GStreamer en `openob-embedded-installer\packaging\gstreamer-*`. El build detectará y copiará esa carpeta a `openob_runtime\gstreamer` y generará un `config/gstreamer.env` con rutas relativas para que la instalación sea relocatable.
- Instala `pip`, dependencias runtime y el paquete `openob`.
- Copia la carpeta `ui/` al runtime embebido (`openob_runtime/ui/`).
- (Opcional) Copia `redis-server/` a `openob_runtime/redis/`.

## 2) Construir el instalador

- Instala Inno Setup 6.
- Ejecuta:

  `powershell -ExecutionPolicy Bypass -File .\openob-embedded-installer\scripts\50_build_installer.ps1`

Salida esperada:

- `openob-embedded-installer/dist/OpenOB-Setup.exe`

## 3) Validación rápida (sin instalar)

- `powershell -ExecutionPolicy Bypass -File .\openob-embedded-installer\scripts\99_verify_install.ps1`

## Notas sobre GStreamer

El instalador **no incluye** GStreamer por defecto, pero puedes incluirlo en el runtime embebido añadiendo una carpeta `gstreamer-*` en `openob-embedded-installer\packaging` (por ejemplo `gstreamer-1.27.50`). El build copiará esa carpeta a `openob_runtime\gstreamer` y generará un `config/gstreamer.env` con rutas relativas para que la instalación sea relocatable.

Si prefieres no bundlear, configura las rutas en `openob_runtime/config/gstreamer.env` o instala GStreamer en:

- `C:\Program Files\gstreamer\1.0\msvc_x86_64`

Nota: `gi` (PyGObject) debe coincidir con la versión ABI de Python usada por el runtime embebido (por ejemplo, para Python 3.14 usa `cp314`).
