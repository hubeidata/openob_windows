@echo off
setlocal

rem OpenOB launcher for embedded Python runtime
set "APPDIR=%~dp0.."
set "PYTHONHOME=%APPDIR%\python"

rem Bundle gvsbuild DLLs
if exist "%APPDIR%\gvsbuild\bin" set "PATH=%APPDIR%\gvsbuild\bin;%PATH%"
rem GStreamer DLLs
if not "%GstBin%"=="" set "PATH=%GstBin%;%PATH%"

rem Ensure bundled gvsbuild DLLs are available for gi
if exist "%APPDIR%\gvsbuild\bin" set "PATH=%APPDIR%\gvsbuild\bin;%PATH%"

rem Load GStreamer env from config (skip comments starting with #)
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%APPDIR%\config\gstreamer.env") do (
  if not "%%A"=="" set "%%A=%%B"
)

rem If GstPySitePackages is not explicitly set, derive it from GstBin
if "%GstPySitePackages%"=="" (
  if not "%GstBin%"=="" (
    rem GstBin typically ends with \bin; use its parent as root
    for %%R in ("%GstBin%\..") do set "GstRoot=%%~fR"
    set "GstPySitePackages=%GstRoot%\lib\site-packages"
  )
)

if not "%GstBin%"=="" set "PATH=%GstBin%;%PATH%"

rem Ensure Python can import gi (PyGObject) from GStreamer runtime
if not "%GstPySitePackages%"=="" (
  if exist "%GstPySitePackages%" (
    if defined PYTHONPATH (
      set "PYTHONPATH=%GstPySitePackages%;%PYTHONPATH%"
    ) else (
      set "PYTHONPATH=%GstPySitePackages%"
    )
  )
)

set "PATH=%PYTHONHOME%;%PYTHONHOME%\Scripts;%PATH%"

"%PYTHONHOME%\python.exe" -m openob %*
