# Packaging

`packaging/openob_runtime/` es el directorio que se copia al destino final del instalador.

Contenido esperado:

- `python/` (descargado y extraído por scripts)
- `bin/openob.cmd` launcher
- `config/gstreamer.env` configuración de GStreamer
- `gstreamer/` (opcional/bundle) copia de una distribución de GStreamer (msvc_x86_64) para incluir en el runtime. El build detectará carpetas `gstreamer-*` en `packaging/` y las copiará aquí, generando `config/gstreamer.env` con rutas relativas.
- `redis/` (opcional) binarios de redis-server para Windows
