@echo off
setlocal

set "APPDIR=%~dp0.."
set "REDISDIR=%APPDIR%\redis"

if not exist "%REDISDIR%\redis-server.exe" (
  echo redis-server.exe not found in %REDISDIR%
  echo Rebuild the runtime with scripts\40_bundle_redis.ps1 or install Redis separately.
  exit /b 2
)

"%REDISDIR%\redis-server.exe" "%REDISDIR%\redis.windows.conf"
