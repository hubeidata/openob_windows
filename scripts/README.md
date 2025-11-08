# Redis service scripts

Two helper PowerShell scripts to install/uninstall the bundled Redis as a Windows service.

Important: Run these scripts from an elevated PowerShell (Run as Administrator).

Install service:

```powershell
# from repo root
.\scripts\install_redis_service.ps1
```

Uninstall service:

```powershell
.# from repo root
.\scripts\uninstall_redis_service.ps1
```

Notes:
- The installer script chooses `redis.network.conf` (if present) or falls back to `redis.windows-service.conf` / `redis.windows.conf`.
- If you prefer to bind Redis only to a specific LAN IP, edit the chosen conf before installing.
- Installing a Redis service exposes the server on boot. Secure it by enabling `requirepass` in the config or restricting access with firewall rules.
