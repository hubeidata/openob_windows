"""LCD 1602 decoder monitor for internet connection via WireGuard.

Requisitos de visualización (LCD 16x2):
- Línea superior: textos de monitoreo (rotativo)
- Línea inferior: niveles de audio RX (L/R) desde el centro hacia los extremos.
  * Nivel bajo = '||' en el centro
  * L crece del centro hacia la izquierda
  * R crece del centro hacia la derecha
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from time import sleep
from typing import Optional, Tuple

import lcddriver


try:
    import redis  # type: ignore
except Exception:
    redis = None


LCD_WIDTH = 16


def _lcd_bar_char() -> str:
    """Return the character used to fill the VU bar on HD44780.

    By default we use 0xFF (full block) which renders as a solid cell on
    most 1602 LCD ROMs. Override with OPENOB_LCD_BAR_CHAR.
    """
    raw = (os.environ.get("OPENOB_LCD_BAR_CHAR", "") or "").strip()
    if not raw:
        return chr(255)
    low = raw.lower()
    if low in {"255", "0xff", "ff", "block", "full"}:
        return chr(255)
    # Use first character if a longer string was provided
    return raw[0]


def _setup_logging() -> logging.Logger:
    """Return a logger configured for diagnostics.

    Logs to /tmp/lcd_decoder_internet.log for debugging audio visualization issues.
    """
    logger = logging.getLogger("openob.lcd.decoder.internet")
    logger.setLevel(logging.DEBUG)
    try:
        logger.handlers.clear()
    except Exception:
        pass

    # Handler para archivo
    handler = logging.FileHandler("/tmp/lcd_decoder_internet.log")
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # No propagar ni deshabilitar para permitir logs
    logger.propagate = False
    logger.disabled = False
    return logger


def _fit_lcd(text: str, width: int = LCD_WIDTH) -> str:
    text = (text or "").replace("\n", " ")
    if len(text) > width:
        return text[:width]
    return text.ljust(width)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _db_to_norm(db: float, min_db: float = -60.0) -> float:
    """Map dB (min_db..0) to 0..1 (linear)."""
    db = max(min_db, min(0.0, db))
    return (db - min_db) / (0.0 - min_db)


def _db_to_norm_scaled(db: float, *, min_db: float, gamma: float, headroom_db: float) -> float:
    """Map dB to 0..1 with extra scaling for better LCD resolution.

    - headroom_db: reserves a little space at the top so peaks at 0dBFS
      don't pin the display at 100% all the time.
    - gamma > 1 compresses the top a bit (more movement near loud levels).
    """
    try:
        db_f = float(db)
    except Exception:
        return 0.0

    # Apply headroom: treat 0dB as -headroom_db for display purposes
    if headroom_db > 0:
        db_f = min(db_f, -abs(headroom_db))

    base = _db_to_norm(db_f, min_db=min_db)
    base = max(0.0, min(1.0, base))
    try:
        return max(0.0, min(1.0, pow(base, gamma)))
    except Exception:
        return base


def render_rx_bar(left_norm: float, right_norm: float) -> str:
    """Render 16 chars: L from center to left, R from center to right."""
    left_norm = max(0.0, min(1.0, left_norm))
    right_norm = max(0.0, min(1.0, right_norm))

    # 16 cols => center uses two chars at positions 7 and 8
    center_l = 7
    center_r = 8
    max_side = 7  # positions away from center on each side

    # Use floor instead of round to avoid pinning at full-scale.
    left_n = int(left_norm * max_side)
    right_n = int(right_norm * max_side)
    left_n = max(0, min(max_side, left_n))
    right_n = max(0, min(max_side, right_n))

    bar = _lcd_bar_char()

    chars = [" "] * LCD_WIDTH
    # Center marker is two filled cells ("||" concept) for better visibility
    chars[center_l] = bar
    chars[center_r] = bar

    for i in range(1, left_n + 1):
        chars[center_l - i] = bar
    for i in range(1, right_n + 1):
        chars[center_r + i] = bar

    return "".join(chars)


@dataclass
class RedisVU:
    left_db: float = -120.0
    right_db: float = -120.0
    updated_ts: Optional[float] = None
    source: str = "peak"


def _redis_client(host: str, port: int = 6379):
    if redis is None:
        return None
    kw = dict(host=host, port=port, db=0, decode_responses=True)
    client = None
    last_err = None
    for variant in ('encoding', 'charset', 'none'):
        try:
            if variant == 'encoding':
                client = redis.StrictRedis(**kw, encoding='utf-8')
            elif variant == 'charset':
                client = redis.StrictRedis(**kw, charset='utf-8')
            else:
                client = redis.StrictRedis(**kw)
            break
        except TypeError as e:
            logging.getLogger('lcd').debug(f"Redis init with {variant} failed: {e}")
            last_err = e
    if client is None:
        return None
    return client


def _fetch_rx_vu(client, link_name: str, logger: Optional[logging.Logger] = None) -> Optional[RedisVU]:
    if client is None:
        if logger:
            logger.error("Redis client is None")
        return None
    key = f"openob:{link_name}:vu:rx"
    try:
        data = client.hgetall(key)
    except Exception as e:
        if logger:
            logger.exception(f"Redis hgetall failed for key={key}: {e}")
        return None
    if logger:
        logger.debug(f"Data from Redis for key={key}: {data}")
    if not data:
        if logger:
            logger.warning(f"No VU data found at key={key}")
        return None

    # Prefer RMS if available (more perceptible movement than peak, which often hits 0dB)
    left = data.get("left_rms_db") or data.get("left_rms")
    right = data.get("right_rms_db") or data.get("right_rms")
    source = "rms" if (left is not None or right is not None) else "peak"
    if left is None and right is None:
        left = data.get("left_db") or data.get("left") or data.get("l")
        right = data.get("right_db") or data.get("right") or data.get("r")
    updated_ts = data.get("updated_ts") or data.get("ts")
    ldb = _safe_float(left, default=-120.0)
    rdb = _safe_float(right, default=ldb)
    uts = _safe_float(updated_ts, default=0.0)
    if logger:
        logger.debug(f"Fetched VU: left_db={ldb}, right_db={rdb}, source={source}, updated_ts={uts}")
    return RedisVU(left_db=ldb, right_db=rdb, updated_ts=(uts if uts > 0 else None), source=source)


def _discover_vu_link_name(client, logger: Optional[logging.Logger] = None) -> Optional[str]:
    """Try to discover a link_name by scanning Redis keys.

    Looks for keys like: openob:<link_name>:vu:rx
    """
    if client is None:
        return None
    try:
        # Prefer scan_iter to avoid blocking.
        for key in client.scan_iter(match="openob:*:vu:rx", count=200):
            try:
                key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
            except Exception:
                key_str = str(key)
            parts = key_str.split(":")
            if len(parts) >= 4 and parts[0] == "openob" and parts[-2] == "vu" and parts[-1] == "rx":
                # openob:<link>:vu:rx
                link = parts[1]
                if logger:
                    logger.info("Discovered VU key=%s (link_name=%s)", key_str, link)
                return link
        return None
    except Exception:
        if logger:
            logger.exception("Failed to scan for VU keys")
        return None


def _cpu_pct_text() -> str:
    # Raspberry/Linux only; if it fails, show N/A
    try:
        cpu = os.popen(
            """grep 'cpu ' /proc/stat | awk '{usage=($2+$4)*100/($2+$4+$5)} END {print usage }'"""
        ).readline().strip()
        return f"CPU {float(cpu):.1f}%"
    except Exception:
        return "CPU N/A"


def _ip_text() -> str:
    try:
        ip = os.popen('hostname -I').readline().strip()
        ip = ip.split()[0] if ip else "-"
        return f"IP {ip}"
    except Exception:
        return "IP -"


def _status_text() -> str:
    try:
        status = os.popen('tail -1 /etc/gui/log/instreamer.log').readline().strip()
        if not status:
            return "Estado -"
        # Keep the last chunk (usually has the useful info)
        return status[-16:]
    except Exception:
        return "Estado -"


def _ping_ms(ip: str, timeout_s: float = 1.0) -> Optional[int]:
    """Return ping latency in ms, or None if unreachable.

    Target platform is Linux/Raspberry Pi.
    """
    if not ip:
        return None
    try:
        # -c 1: one packet
        # -W 1: timeout (seconds) on Linux ping
        # Use a short overall timeout as well.
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(int(max(1, round(timeout_s)))), ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s + 0.5,
        )
        if proc.returncode != 0:
            return None

        # Parse time=XX ms
        out = proc.stdout or ""
        marker = "time="
        if marker in out:
            tail = out.split(marker, 1)[1]
            num = ""
            for ch in tail:
                if ch.isdigit() or ch == '.':
                    num += ch
                else:
                    break
            if num:
                return int(round(float(num)))
        return 1
    except Exception:
        return None


def _ping_text(label: str, ip: str, timeout_s: float = 1.0) -> str:
    ms = _ping_ms(ip, timeout_s=timeout_s)
    if ms is None:
        # Example: "GW OFF" (fits 16)
        return f"{label} OFF"
    # Example: "GW 12ms"
    return f"{label} {ms}ms"


def _get_gateway_ip() -> str:
    """Obtener la IP del gateway por defecto automáticamente."""
    try:
        result = subprocess.run(['ip', 'route'], capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if 'default' in line:
                parts = line.split()
                if len(parts) > 2:
                    return parts[2]
    except Exception:
        pass
    return "192.168.1.1"  # Fallback si no se puede detectar


def _get_wireguard_ip(interface: str = "wg0") -> Optional[str]:
    """Obtener la IP asignada a la interfaz WireGuard."""
    try:
        result = subprocess.run(['ip', 'addr', 'show', interface], capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if 'inet ' in line:
                ip = line.split()[1].split('/')[0]
                return ip
    except Exception:
        pass
    return None


def _infer_wireguard_ips(wg_ip: Optional[str]) -> Tuple[str, str]:
    """Inferir IPs del server y decoder basadas en la IP de WireGuard (asumiendo subnet /24)."""
    if wg_ip:
        parts = wg_ip.split('.')
        if len(parts) == 4:
            subnet = '.'.join(parts[:3])
            server_ip = f"{subnet}.1"
            decoder_ip = f"{subnet}.2"
            return server_ip, decoder_ip
    # Fallback
    return "10.13.0.1", "10.13.0.2"


def main() -> int:
    logger = _setup_logging()
    display = lcddriver.lcd()
    display.lcd_clear()

    # Configuración automática
    gateway_ip = _get_gateway_ip()
    wg_ip = _get_wireguard_ip()
    wireguard_server_ip, wireguard_decoder_ip = _infer_wireguard_ips(wg_ip)

    # Permitir override con variables de entorno si es necesario
    gateway_ip = os.environ.get("OPENOB_GATEWAY_IP", gateway_ip)
    wireguard_server_ip = os.environ.get("OPENOB_WIREGUARD_SERVER_IP", wireguard_server_ip)
    wireguard_decoder_ip = os.environ.get("OPENOB_WIREGUARD_DECODER_IP", wireguard_decoder_ip)

    # Redis host es el decoder en la red WireGuard
    redis_host = os.environ.get("OPENOB_REDIS_HOST", wireguard_decoder_ip)
    redis_port = int(os.environ.get("OPENOB_REDIS_PORT", "6379"))
    link_name = os.environ.get("OPENOB_LINK_NAME", "transmission")
    vu_link_name = link_name

    logger.info(f"Gateway IP: {gateway_ip}")
    logger.info(f"WireGuard IP: {wg_ip}")
    logger.info(f"WireGuard Server IP: {wireguard_server_ip}")
    logger.info(f"WireGuard Decoder IP: {wireguard_decoder_ip}")
    logger.info(f"Redis Host: {redis_host}")

    client = _redis_client(redis_host, redis_port)
    if client is None:
        logger.error("Failed to create Redis client")
    else:
        try:
            client.ping()
            logger.info("Redis client ping successful")
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            client = None

    # Splash
    display.lcd_display_string(_fit_lcd("LINK DE AUDIO"), 1)
    display.lcd_display_string(_fit_lcd("VIA INTERNET"), 2)
    sleep(2)

    monitor_i = 0
    current_top = ""
    next_monitor_change = 0.0

    discover_every_s = float(os.environ.get("OPENOB_LCD_DISCOVER_EVERY_S", "5.0"))
    next_discover = 0.0

    # Refresh rate for the LCD loop (audio bar)
    refresh_s = float(os.environ.get("OPENOB_LCD_REFRESH_S", "0.08"))
    refresh_s = max(0.02, min(1.0, refresh_s))

    # Ping timeout: keep small so pings don't freeze LCD updates
    ping_timeout_s = float(os.environ.get("OPENOB_LCD_PING_TIMEOUT_S", "0.35"))
    ping_timeout_s = max(0.1, min(2.0, ping_timeout_s))

    monitors = [
        lambda: _ping_text("GW", gateway_ip, timeout_s=ping_timeout_s),
        lambda: _ping_text("WG SVR", wireguard_server_ip, timeout_s=ping_timeout_s),
        lambda: _ping_text("WG DEC", wireguard_decoder_ip, timeout_s=ping_timeout_s),
        _ip_text,
    ]

    # LCD VU scaling (tune to match UI feel)
    # Typical useful defaults for speech/music with 7 segments per side.
    vu_min_db = float(os.environ.get("OPENOB_LCD_VU_MIN_DB", "-60"))
    vu_gamma = float(os.environ.get("OPENOB_LCD_VU_GAMMA", "1.6"))
    vu_headroom_db = float(os.environ.get("OPENOB_LCD_VU_HEADROOM_DB", "1.0"))

    last_log_time = 0.0
    log_interval = 10.0  # Log VU status every 10 seconds

    try:
        while True:
            now = time.time()
            if now >= next_monitor_change:
                monitor_i = (monitor_i + 1) % len(monitors)
                # Only run ping when changing the top line so it doesn't block the fast bar refresh.
                current_top = monitors[monitor_i]()
                next_monitor_change = now + 3.0

            if not current_top:
                current_top = monitors[monitor_i]()
            top = current_top

            vu = _fetch_rx_vu(client, vu_link_name, logger=logger)
            if now - last_log_time > log_interval:
                if vu is None:
                    logger.warning("VU data is None - no audio variation detected")
                else:
                    logger.info(f"VU data: left_db={vu.left_db:.1f}, right_db={vu.right_db:.1f}, source={vu.source}")
                last_log_time = now

            if vu is None:
                # no data: center marker only
                bottom = render_rx_bar(0.0, 0.0)

                # If VU is missing, try to discover correct link_name in Redis
                if client is not None and now >= next_discover:
                    discovered = _discover_vu_link_name(client, logger=logger)
                    if discovered and discovered != vu_link_name:
                        logger.info(f"Discovered new VU link_name: {discovered}")
                        vu_link_name = discovered
                    next_discover = now + max(1.0, discover_every_s)
            else:
                left_norm = _db_to_norm_scaled(
                    vu.left_db,
                    min_db=vu_min_db,
                    gamma=vu_gamma,
                    headroom_db=vu_headroom_db,
                )
                right_norm = _db_to_norm_scaled(
                    vu.right_db,
                    min_db=vu_min_db,
                    gamma=vu_gamma,
                    headroom_db=vu_headroom_db,
                )
                bottom = render_rx_bar(left_norm, right_norm)

            display.lcd_display_string(_fit_lcd(top), 1)
            display.lcd_display_string(_fit_lcd(bottom), 2)
            sleep(refresh_s)

    except KeyboardInterrupt:
        display.lcd_display_string(_fit_lcd("Borrando"), 1)
        display.lcd_display_string(_fit_lcd(""), 2)
        sleep(0.5)
        display.lcd_clear()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())