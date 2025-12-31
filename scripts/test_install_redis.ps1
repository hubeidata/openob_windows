<#
Comprueba la instalación de Redis en Windows e informa la(s) versión(es).

Uso:
  .\scripts\test_install_redis.ps1
  .\scripts\test_install_redis.ps1 -ServiceName "redis"  # si el servicio tiene otro nombre
Salida:
  Código 0 = se encontró al menos una versión (cliente/servidor/servicio)
  Código 2 = no se detectó Redis
#>

[CmdletBinding()]
param(
    [string]$ServiceName = 'redis'
)

$found = $false

Write-Host "=== Comprobando redis-cli en PATH ==="
$cli = Get-Command redis-cli -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
if ($cli) {
    $cliVer = & $cli --version 2>&1
    Write-Host "redis-cli: $cli"
    Write-Host "redis-cli --version: $cliVer"
    $found = $true
} else {
    Write-Warning "redis-cli no encontrado en PATH."
}

Write-Host "`n=== Comprobando redis-server en PATH ==="
$server = Get-Command redis-server -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue
if ($server) {
    $srvVer = & $server --version 2>&1
    Write-Host "redis-server: $server"
    Write-Host "redis-server --version: $srvVer"
    $found = $true
} else {
    Write-Warning "redis-server no encontrado en PATH."
}

Write-Host "`n=== Buscando servicio Windows relacionado con Redis ('$ServiceName*') ==="
$svcMatches = Get-Service -Name "$ServiceName*" -ErrorAction SilentlyContinue
if ($svcMatches) {
    foreach ($svc in $svcMatches) {
        Write-Host "Servicio: $($svc.Name) - Estado: $($svc.Status)"
        try {
            $winSvc = Get-CimInstance Win32_Service -Filter "Name='$($svc.Name)'" -ErrorAction Stop
            Write-Host "PathName: $($winSvc.PathName)"
        } catch {
            Write-Warning "No se pudo obtener PathName para el servicio $($svc.Name)."
        }
        $found = $true
    }
} else {
    Write-Host "No se encontraron servicios Windows que coincidan con '$ServiceName*'."
}

# Si disponemos de redis-cli intentamos consultar la versión del servidor (si está en ejecución y accesible)
if ($cli) {
    Write-Host "`n=== Intentando obtener redis_version del servidor (INFO server) ==="
    $info = & $cli INFO server 2>&1

    # Si no hay respuesta intenta conectar explícitamente a 127.0.0.1:6379
    if (-not $info -or ($info -is [System.Array] -and $info.Length -eq 0) -or ($info -is [string] -and $info.Trim() -eq '')) {
        Write-Host "No se obtuvo respuesta con 'redis-cli INFO server'. Probando conexión a 127.0.0.1:6379..."
        $info = & $cli -h 127.0.0.1 -p 6379 INFO server 2>&1
    }

    # Normalizar salida a cadena para aplicar la regex de forma segura
    $infoStr = [string]::Join("`n", @( $info | ForEach-Object { $_.ToString() } ))

    $match = [regex]::Match($infoStr, 'redis_version:\s*(\S+)')
    if ($match.Success) {
        Write-Host "redis server version: $($match.Groups[1].Value)"
        $found = $true
    } elseif ($infoStr -match 'NOAUTH') {
        Write-Warning "Servidor requiere autenticación (NOAUTH). No fue posible leer INFO server sin credenciales."
        $found = $true
    } elseif ($infoStr -match 'ERR|error') {
        Write-Warning "Respuesta de redis-cli: $infoStr"
    } else {
        Write-Host "No se pudo obtener redis_version. redis-cli devolvió:" 
        Write-Host $infoStr
    }
}

# Verify environment variables set by installer
$envCheckOk = $true
Write-Host "`n=== Verificando variables de entorno a nivel Máquina ==="
$redisHomeEnv = [Environment]::GetEnvironmentVariable('REDIS_HOME','Machine')
if ($redisHomeEnv) {
    Write-Host "REDIS_HOME=$redisHomeEnv"
    if ($env:Path -notlike "*$redisHomeEnv*") {
        Write-Warning "REDIS_HOME no está en PATH de la sesión actual."
    }
} else {
    Write-Warning "REDIS_HOME no está configurado a nivel Máquina."
    $envCheckOk = $false
}
$redisConfEnv = [Environment]::GetEnvironmentVariable('REDIS_CONF','Machine')
if ($redisConfEnv) {
    Write-Host "REDIS_CONF=$redisConfEnv"
} else {
    Write-Warning "REDIS_CONF no está configurado a nivel Máquina."
    $envCheckOk = $false
}
$svcNameEnv = [Environment]::GetEnvironmentVariable('REDIS_SERVICE_NAME','Machine')
if ($svcNameEnv) { Write-Host "REDIS_SERVICE_NAME=$svcNameEnv" } else { Write-Warning "REDIS_SERVICE_NAME no está configurado a nivel Máquina."; $envCheckOk = $false }

if (-not $found) {
    Write-Error "No se detectó Redis (ni cliente, ni servidor, ni servicio)."
    exit 2
}

if (-not $envCheckOk) {
    Write-Error "Comprobación incompleta: variables de entorno faltantes";
    exit 3
}

Write-Host "`nComprobación completada."
exit 0