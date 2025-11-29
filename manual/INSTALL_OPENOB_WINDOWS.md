# Instalación rápida de OpenOB en Windows

Este documento contiene los comandos mínimos y reproducibles que funcionaron en este entorno Windows. Ejecuta los pasos desde la carpeta raíz del workspace (por ejemplo: C:\Users\vamanuel\Documents\openob_windows).

Requisitos previos
- Python 3.12 x64 instalado (asegúrate de que coincida con la ABI usada por PyGObject/GStreamer si usas gi).
- GStreamer runtime MSVC x86_64 instalado (por defecto en C:\Program Files\gstreamer\1.0\msvc_x86_64).
(https://gstreamer.freedesktop.org/download/#windows)
- Descomprimir los binarios de Redis en la carpeta `redis-server` (ya incluidos en este workspace).

1) Clonar / preparar el repositorio

    git clone https://github.com/JamesHarrison/openob.git openob
    cd openob

2) Crear y activar entorno virtual
	En powershell como administrador:
	Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

3) Instalar OpenOB en el venv y dependencias compatibles
	Nada de errores
    
    python -m pip install --upgrade pip
    pip install 'redis<4.0,>=3.5.3' pystray pillow setuptools wheel


    cd .\openob\
    pip install .

4) Hacer accesibles los bindings de GStreamer en el venv

Si tienes GStreamer instalado en C:\Program Files\gstreamer\1.0\msvc_x86_64, crea un archivo .pth dentro de tu site-packages para exponer sus site-packages a Python:
Si GStreamer está instalado en la ruta por defecto, crea un `.pth` en el `site-packages` del venv:

    Set-Content -Encoding ASCII -Path .\.venv\Lib\site-packages\gstreamer.pth -Value "C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\site-packages"

Además, para la sesión PowerShell en la que lances OpenOB añade:

    $env:PATH += ';C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'
    $env:GI_TYPELIB_PATH = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'

Comprueba desde el venv que `gi`/`Gst` importan:

    .\.venv\Scripts\python.exe -c "import gi; from gi.repository import Gst; print('GStreamer OK')"


5) Iniciar Redis (temporalmente manual)



O instalarlo como servicio (requiere PowerShell elevado):

    .\scripts\install_redis_service.ps1

Verifica que Redis está escuchando:

    Test-NetConnection -ComputerName 127.0.0.1 -Port 6379

6) Ejecutar OpenOB

# Instalación rápida de OpenOB en Windows (actualizado)

Este documento contiene los comandos mínimos y reproducibles para preparar el entorno y lanzar OpenOB en Windows asumiendo que Redis ya está instalado y configurado como servicio del sistema (es decir, Redis ya arranca con Windows y escucha en 127.0.0.1:6379).

Ejecuta los pasos desde la carpeta raíz del workspace (por ejemplo: `C:\Users\vamanuel\Documents\openob_windows`).

Requisitos previos
- Python 3.13 x64 instalado.
- GStreamer runtime MSVC x86_64 instalado (por defecto: `C:\Program Files\gstreamer\1.0\msvc_x86_64`).
- Redis instalado como servicio Windows y en ejecución (si no lo está, hay scripts en `scripts\` para instalarlo).

1) Clonar / preparar el repositorio

    git clone https://github.com/JamesHarrison/openob.git openob
    cd openob

2) Crear y activar entorno virtual

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

3) Instalar OpenOB y dependencias compatibles en el venv

    .\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
    .\.venv\Scripts\python.exe -m pip install "redis<4.0,>=3.5.3"
	cd openob
	..\.venv\Scripts\python.exe -m pip install .
    

4) Exponer los bindings de GStreamer al venv

Si GStreamer está instalado en la ruta por defecto, crea un `.pth` en el `site-packages` del venv:

    Set-Content -Encoding ASCII -Path .\.venv\Lib\site-packages\gstreamer.pth -Value "C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\site-packages"

Además, para la sesión PowerShell en la que lances OpenOB añade:

    $env:PATH += ';C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'
    $env:GI_TYPELIB_PATH = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'

Comprueba desde el venv que `gi`/`Gst` importan:

    .\.venv\Scripts\python.exe -c "import gi; from gi.repository import Gst; print('GStreamer OK')"

5) Verificar que Redis está instalado y en ejecución como servicio

Comprueba el estado del servicio Redis en PowerShell:

    Get-Service -Name Redis

Si ves `Status : Running` estás listo. Si el servicio existe pero está detenido, arráncalo:

    Start-Service -Name Redis

Si no tienes Redis instalado como servicio y quieres instalarlo, hay un script auxiliar (requiere PowerShell elevado):

    .\scripts\install_redis_service.ps1

6) Lanzar OpenOB usando el helper (asume Redis ya instalado)

Usa el nuevo script PowerShell que configura el entorno GStreamer para la sesión y arranca OpenOB desde el venv:

En la carpeta raíz del workspace (no es necesario activar el venv manualmente porque el script invoca la Python del venv):

    .\scripts\start_openob.ps1 -OpenobArgs '-v 127.0.0.1 emetteur transmission tx 192.168.1.17 -e pcm -r 48000 -j 60 -a auto'

Opciones útiles:
- `-Background` : lanza OpenOB en background.
- `-ForceRun` : no preguntar si Redis no responde localmente; continuar.

Nota: el script por defecto usa `..\.venv\Scripts\python.exe` y `..\.venv\Scripts\openob` dentro del workspace; ajusta los parámetros si tu venv está en otra ubicación.

Comprobación rápida (si quieres hacerlo manualmente):

    # verificar Redis
    Test-NetConnection -ComputerName 127.0.0.1 -Port 6379

    # lanzar OpenOB (sesión):
    $env:PATH += ';C:\Program Files\gstreamer\1.0\msvc_x86_64\bin'
    $env:GI_TYPELIB_PATH = 'C:\Program Files\gstreamer\1.0\msvc_x86_64\lib\girepository-1.0'
    .\.venv\Scripts\python.exe .\.venv\Scripts\openob -v 127.0.0.1 emetteur transmission tx 192.168.8.17 -e pcm -r 48000 -j 60 -a test

Notas de seguridad
- Este manual asume Redis accesible en 127.0.0.1. Si tu servicio Redis escucha en otra IP o requiere contraseña, ajusta la conexión o usa el script de instalación para cambiar la configuración.
- No expongas Redis sin protegerlo en producción (use `requirepass` y/o límite de bind a IPs internas).

Archivos relevantes
- `scripts\start_openob.ps1` — helper para arrancar OpenOB (asume Redis en ejecución).
- `scripts\install_redis_service.ps1` / `scripts\uninstall_redis_service.ps1` — instalar/desinstalar Redis como servicio (opcional).
- `ui\main.py` — interfaz Tkinter para controlar arranque/parada (opcional).

Si quieres que haga una pasada final para eliminar secciones duplicadas y dejar un README muy corto con solo los comandos copy/paste listos, lo hago ahora.
