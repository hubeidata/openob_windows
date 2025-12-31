# Comprobar Redis desde el runtime embebido o desde un Python específico
# Uso:
#   .\scripts\test_embebido_redis.ps1
#   .\scripts\test_embebido_redis.ps1 -PythonExe 'C:\Path\To\python.exe' -RedisHost 127.0.0.1 -RedisPort 6379
# Salida/exit codes:
#   0 = Redis accesible y redis-py OK
#   1 = Python no encontrado
#   2 = redis-cli no disponible y redis-py falla
#   3 = fallo de import/conexión con redis-py (ver traceback)

[CmdletBinding()]
param(
    [string]$PythonExe,
    [string]$EmbeddedPath = 'C:\Users\Soporte\AppData\Local\Programs\OpenOB\python\python.exe',
    [string]$RedisHost = '127.0.0.1',
    [int]$RedisPort = 6379
)

$repoRoot = Split-Path -Parent $PSScriptRoot
# Use only the embedded Python specified by $EmbeddedPath unless -PythonExe overrides it.
if ($PythonExe) {
    if (Test-Path $PythonExe) { $python = $PythonExe }
    else { Write-Error "El ejecutable proporcionado en -PythonExe no existe: $PythonExe"; exit 1 }
} else {
    if (Test-Path $EmbeddedPath) { $python = $EmbeddedPath }
    else {
        Write-Error "Python embebido no encontrado en la ruta esperada: $EmbeddedPath"
        exit 1
    }
}

if (-not $python) {
    Write-Error "Python no encontrado (ni runtime embebido ni en PATH)."
    exit 1
}
Write-Host "Usando Python: $python"

Write-Host "`n=== Estado servicio Redis (si existe) ==="
$svc = Get-Service -Name Redis -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Servicio Redis: $($svc.Name) - Estado: $($svc.Status)"
    try { $winSvc = Get-CimInstance Win32_Service -Filter "Name='Redis'"; Write-Host "PathName: $($winSvc.PathName)" } catch {}
} else { Write-Host "Servicio 'Redis' no encontrado." }

Write-Host "`n=== Variables de entorno (Machine) relacionadas ==="
$envVars = @('REDIS_HOME','REDIS_CONF','REDIS_SERVICE_NAME')
foreach ($v in $envVars) {
    $val = [Environment]::GetEnvironmentVariable($v,'Machine')
    if ($val) { Write-Host "$v=$val" } else { Write-Warning "$v no está configurado a nivel Machine." }
}

Write-Host "`n=== Comprobando redis-cli ==="
$cli = Get-Command redis-cli -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
$cliAvailable = $false
if ($cli) {
    $cliAvailable = $true
    try {
        $ping = & $cli -h $RedisHost -p $RedisPort PING 2>&1
        Write-Host "redis-cli PING: $ping"
        $info = & $cli -h $RedisHost -p $RedisPort INFO server 2>$null
        if ($info) {
            $ver = ($info | Select-String 'redis_version' -SimpleMatch).ToString()
            Write-Host "redis-cli INFO server: $ver"
        }
    } catch {
        Write-Warning "redis-cli fallo al conectar: $_"
    }
} else {
    Write-Warning "redis-cli no encontrado en PATH."
}

Write-Host "`n=== Comprobando redis-py desde Python: intentando importar y conectar ==="
$py = @"
import sys,traceback
host = r"$RedisHost"
port = $RedisPort
try:
    import redis
    print('redis-py:', getattr(redis, '__version__', '<no version>'))
    try:
        r = redis.Redis(host=host, port=port, socket_connect_timeout=2)
        print('PING ->', r.ping())
        info = r.info()
        print('INFO redis_version:', info.get('redis_version'))
        r.set('openob_test_key', 'ok', ex=5)
        print('SET/GET ->', r.get('openob_test_key'))
    except Exception as e:
        print('Conexión/operación Redis fallo:', e)
        traceback.print_exc()
        sys.exit(3)
    try:
        _ = redis.Redis(host=host, port=port, charset='utf-8')
        print("Constructor con 'charset' aceptado (ok).")
    except TypeError as e:
        print("Constructor con 'charset' falló (TypeError):", e)
    sys.exit(0)
except Exception as e:
    print('ERROR al importar/usar redis:', e)
    traceback.print_exc()
    sys.exit(3)
"@

$tempFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "check_redis_{0}.py" -f ([System.Guid]::NewGuid().ToString()))
Set-Content -Path $tempFile -Value $py -Encoding UTF8
try {
    $out = & $python $tempFile 2>&1
    Write-Host $out
    $pyLast = $LASTEXITCODE
} finally {
    Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
}

if ($pyLast -eq 0) {
    Write-Host "`nRESULT: Redis accesible y redis-py OK"
    exit 0
} elseif (-not $cliAvailable -and $pyLast -ne 0) {
    Write-Error "`nRESULT: redis-cli no disponible y redis-py falla. Revisa instalación de Redis y redis-py."
    exit 2
} else {
    Write-Error "`nRESULT: fallo en la comprobación de Redis (exit $pyLast)."
    exit 3
}