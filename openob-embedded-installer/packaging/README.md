# Packaging

`packaging/openob_runtime/` es el directorio que se copia al destino final del instalador.

Contenido esperado:

- `python/` (descargado y extraído por scripts)
- `bin/openob.cmd` launcher
- `config/gstreamer.env` configuración de GStreamer
- `redis/` (opcional) binarios de redis-server para Windows
