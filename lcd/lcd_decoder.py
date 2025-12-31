"""LCD 1602 decoder monitor.

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
import math
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
    """Return a logger. Disabled by default unless OPENOB_LCD_DEBUG is set.

    The LCD runs in a tight loop; logging can create I/O overhead and fill
    storage on embedded devices. Enable debug with OPENOB_LCD_DEBUG=1.
    """
    logger = logging.getLogger("openob.lcd.decoder")
    try:
        logger.handlers.clear()
    except Exception:
        pass

    debug = os.environ.get("OPENOB_LCD_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    log_file = os.environ.get("OPENOB_LCD_LOG_FILE", "").strip()

    if debug:
        logger.disabled = False
        logger.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        if log_file:
            try:
                fh = logging.FileHandler(log_file)
                fh.setFormatter(fmt)
                logger.addHandler(fh)
            except Exception:
                sh = logging.StreamHandler()
                sh.setFormatter(fmt)
                logger.addHandler(sh)
                logger.exception("Failed to open log file %s; falling back to stderr", log_file)
        else:
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        logger.info("LCD decoder logging enabled (debug mode)")
    else:
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        logger.disabled = True

    logger.propagate = False
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


def _fetch_rx_vu(client, link_name: str, direction: str = "rx", logger: Optional[logging.Logger] = None) -> Optional[RedisVU]:
    if client is None:
        return None

    # Allow passing a full Redis key (starting with 'openob:') or a link name
    if link_name and isinstance(link_name, str) and link_name.startswith("openob:") and ":vu:" in link_name:
        key = link_name
    else:
        key = f"openob:{link_name}:vu:{direction}"

    if logger and logger.isEnabledFor(logging.DEBUG):
        logger.debug("Fetching VU from Redis key=%s", key)

    try:
        data = client.hgetall(key)
    except Exception:
        if logger:
            logger.exception("Redis hgetall failed for key=%s", key)
        return None
    if not data:
        if logger:
            logger.debug("No VU data found at key=%s", key)
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

    # If there's VU values but no updated_ts, assume the data is fresh and use current time.
    if uts <= 0.0 and (left is not None or right is not None):
        if logger:
            try:
                logger.debug("VU key %s missing updated_ts; assuming fresh (now=%.3f)", key, time.time())
            except Exception:
                pass
        uts = time.time()

    return RedisVU(left_db=ldb, right_db=rdb, updated_ts=(uts if uts > 0 else None), source=source)


def _discover_vu_link_name(client, direction: str = "rx", logger: Optional[logging.Logger] = None) -> Optional[str]:
    """Try to discover a link_name by scanning Redis keys.

    Looks for keys like: openob:<link_name>:vu:<direction>
    """
    if client is None:
        return None
    try:
        # Prefer scan_iter to avoid blocking. First try preferred direction.
        pattern = f"openob:*:vu:{direction}"
        found = None
        for key in client.scan_iter(match=pattern, count=200):
            try:
                key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
            except Exception:
                key_str = str(key)
            parts = key_str.split(":")
            if len(parts) >= 4 and parts[0] == "openob" and parts[-2] == "vu" and parts[-1] == direction:
                link = parts[1]
                if logger:
                    logger.info("Discovered VU key=%s (link_name=%s, dir=%s)", key_str, link, direction)
                return link

        # If none found and direction was 'rx', check for 'tx' keys and warn
        if direction == "rx":
            other_found = False
            for key in client.scan_iter(match="openob:*:vu:tx", count=200):
                other_found = True
                try:
                    key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
                except Exception:
                    key_str = str(key)
                if logger:
                    logger.warning("Found only TX VU keys (%s) when configured for RX; consider setting OPENOB_LCD_VU_DIRECTION=tx or explicit OPENOB_LCD_VU_KEY", key_str)
                break
            if other_found:
                return None
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


def _ping_ok(ip: str, timeout_s: float = 1.0) -> bool:
    """Return True if a single ping succeeds (no output)."""
    if not ip:
        return False
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(int(max(1, round(timeout_s)))), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_s + 0.5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def check_consecutive_pings(host: str, count: int = 3, timeout_s: float = 1.0, logger: Optional[logging.Logger] = None) -> bool:
    """Return True if host responds to `count` consecutive pings.

    Uses _ping_ok and returns quickly on first failure.
    """
    if not host or count <= 0:
        return False
    for i in range(count):
        ok = _ping_ok(host, timeout_s=timeout_s)
        if logger and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Ping check %d/%d to %s -> %s", i + 1, count, host, ok)
        if not ok:
            return False
    return True


def _ping_text(label: str, ip: str, timeout_s: float = 1.0) -> str:
    ms = _ping_ms(ip, timeout_s=timeout_s)
    if ms is None:
        # Example: "ANT RX OFF" (fits 16)
        return f"{label} OFF"
    # Example: "ANT RX 12ms"
    return f"{label} {ms}ms"


def get_default_gateway() -> Optional[str]:
    try:
        out = subprocess.check_output(["ip", "route"], text=True)
        for line in out.splitlines():
            if line.startswith("default"):
                parts = line.split()
                # default via <gateway> dev <dev>
                if "via" in parts:
                    return parts[parts.index("via") + 1]
        return None
    except Exception:
        return None


def check_hosts_status(encoder_ip: str, redis_host: str, gateway_ip: Optional[str], timeout_s: float = 0.6, logger: Optional[logging.Logger] = None) -> Tuple[bool, str]:
    """Ping encoder, redis host and gateway, return (all_ok, message)

    Message is short and fits 16 chars (for LCD top line alerts).
    """
    statuses = {}
    try:
        statuses['ENC'] = _ping_ok(encoder_ip, timeout_s=timeout_s)
    except Exception:
        statuses['ENC'] = False
    try:
        statuses['RED'] = _ping_ok(redis_host, timeout_s=timeout_s)
    except Exception:
        statuses['RED'] = False
    try:
        if gateway_ip:
            statuses['GW'] = _ping_ok(gateway_ip, timeout_s=timeout_s)
        else:
            statuses['GW'] = False
    except Exception:
        statuses['GW'] = False

    # Build message: list failing components
    failing = [k for k, v in statuses.items() if not v]
    if not failing:
        return True, "OK"
    # Compact message, e.g., "ENC OFF" or "ENC,RED OFF"
    msg = ",".join(failing) + " OFF"
    # Fit 16 chars
    if len(msg) > 16:
        msg = msg[:16]
    if logger and logger.isEnabledFor(logging.DEBUG):
        logger.debug("Host statuses: %s -> %s", statuses, msg)
    return False, msg


def main() -> int:
    logger = _setup_logging()
    display = lcddriver.lcd()
    display.lcd_clear()

    antena_rx_ip = os.environ.get("OPENOB_ANTENA_RX_IP", "192.168.1.1")
    antena_tx_ip = os.environ.get("OPENOB_ANTENA_TX_IP", "10.13.14.1")
    encoder_ip = os.environ.get("OPENOB_ENCODER_IP", "10.13.14.2")

    # Redis host defaults to the encoder IP because OpenOB publishes VU to the config-host.
    redis_host = os.environ.get("OPENOB_REDIS_HOST", encoder_ip)
    redis_port = int(os.environ.get("OPENOB_REDIS_PORT", "6379"))
    link_name = os.environ.get("OPENOB_LINK_NAME", "transmission")
    vu_link_name = link_name

    # Which direction to read VU from: 'rx' (default) or 'tx'
    vu_direction = os.environ.get("OPENOB_LCD_VU_DIRECTION", "rx").lower()
    if vu_direction not in {"rx", "tx"}:
        vu_direction = "rx"

    # Optional: override full Redis key (e.g. 'openob:myLink:vu:rx')
    vu_key_override = os.environ.get("OPENOB_LCD_VU_KEY", "").strip()
    if vu_key_override:
        if logger and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Using explicit VU key override: %s", vu_key_override)
    else:
        if logger and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Using link_name=%s and direction=%s for VU", vu_link_name, vu_direction)

    client = _redis_client(redis_host, redis_port)
    if client is None:
        logger.info("Redis client unavailable (redis module missing or failed to construct)")
    else:
        try:
            client.ping()
        except Exception:
            logger.warning("Redis ping failed to %s:%d - disabling Redis client", redis_host, redis_port)
            client = None

    # --- GPIO startup & ping-based control ---
    gpio_pin = int(os.environ.get("OPENOB_GPIO_PIN", "4"))
    gpio_init = int(os.environ.get("OPENOB_GPIO_INIT", "1"))
    gpio_check_s = float(os.environ.get("OPENOB_GPIO_CHECK_S", "1.0"))
    gpio_ping_count = int(os.environ.get("OPENOB_GPIO_PING_COUNT", "3"))

    last_gpio_check = 0.0
    current_gpio_state: Optional[int] = None

    # Initialize GPIO pin mode and set initial state
    try:
        subprocess.run(["gpio", "-g", "mode", str(gpio_pin), "output"], check=True)
        subprocess.run(["gpio", "-g", "write", str(gpio_pin), str(gpio_init)], check=True)
        current_gpio_state = gpio_init
        if logger and logger.isEnabledFor(logging.DEBUG):
            logger.info("GPIO pin %d initialized output and set to %d", gpio_pin, gpio_init)
    except Exception:
        if logger:
            logger.exception("Failed to initialize GPIO pin %d (gpio command may be missing or require root)", gpio_pin)
        current_gpio_state = None

    # Splash
    display.lcd_display_string(_fit_lcd("LINK DE AUDIO"), 1)
    display.lcd_display_string(_fit_lcd("DECODER RX"), 2)
    sleep(2)

    monitor_i = 0
    current_top = ""
    next_monitor_change = 0.0

    discover_every_s = float(os.environ.get("OPENOB_LCD_DISCOVER_EVERY_S", "5.0"))
    next_discover = 0.0

    # Refresh rate for the LCD loop (audio bar)
    refresh_s = float(os.environ.get("OPENOB_LCD_REFRESH_S", "0.04"))
    refresh_s = max(0.02, min(1.0, refresh_s))

    # Host health check interval and alert behavior
    host_check_s = float(os.environ.get("OPENOB_LCD_HOST_CHECK_S", "2.0"))
    next_host_check = 0.0
    host_alert = False
    host_alert_msg = ""

    # Determine gateway IP (auto-detect or use env override)
    gateway_ip = os.environ.get("OPENOB_GATEWAY_IP", get_default_gateway() or "")

    # Ping timeout: keep small so pings don't freeze LCD updates
    ping_timeout_s = float(os.environ.get("OPENOB_LCD_PING_TIMEOUT_S", "0.35"))
    ping_timeout_s = max(0.1, min(2.0, ping_timeout_s))

    monitors = [
        lambda: _ping_text("GATEWAY", gateway_ip if gateway_ip else antena_rx_ip, timeout_s=ping_timeout_s),
        lambda: _ping_text("SERVER", antena_tx_ip, timeout_s=ping_timeout_s),
        lambda: _ping_text("ENCODER", encoder_ip, timeout_s=ping_timeout_s),
        _ip_text,
    ]

    # LCD VU scaling (tune to match UI feel)
    # Typical useful defaults for speech/music with 7 segments per side.
    vu_min_db = float(os.environ.get("OPENOB_LCD_VU_MIN_DB", "-30"))
    vu_gamma = float(os.environ.get("OPENOB_LCD_VU_GAMMA", "1.6"))
    vu_headroom_db = float(os.environ.get("OPENOB_LCD_VU_HEADROOM_DB", "1.0"))
    # Redis polling & smoothing (tweak for responsive display without overloading Redis or LCD)
    redis_poll_s = float(os.environ.get("OPENOB_LCD_REDIS_POLL_S", "0.1"))  # poll Redis at 10 Hz by default
    last_vu_fetch = 0.0
    disp_left = 0.0
    disp_right = 0.0
    target_left = 0.0
    target_right = 0.0
    # Smoothing & release/attack tuning
    vu_smooth_tau = float(os.environ.get("OPENOB_LCD_VU_SMOOTH_TAU", "0.06"))  # default attack time (s)
    vu_release_tau = float(os.environ.get("OPENOB_LCD_VU_RELEASE_TAU", "0.02"))  # faster release for quick drop (s)
    vu_stale_drop_s = float(os.environ.get("OPENOB_LCD_VU_STALE_DROP_S", "0.5"))

    # Silence detection: when both channels are below target threshold for N consecutive samples
    vu_silence_target = float(os.environ.get("OPENOB_LCD_VU_SILENCE_TARGET", "0.04"))
    vu_silence_samples = int(os.environ.get("OPENOB_LCD_VU_SILENCE_SAMPLES", "2"))
    vu_silence_counter = 0

    # Sensitivity multiplier to make low dB more visible (use >1 to increase movement)
    vu_sensitivity = float(os.environ.get("OPENOB_LCD_VU_SENSITIVITY", "1.0"))

    # Snap-to-zero behaviour: when target == 0, optionally snap immediately to zero
    vu_snap_to_zero = os.environ.get("OPENOB_LCD_VU_SNAP_TO_ZERO", "1").lower() in {"1", "true", "yes", "on"}
    vu_snap_threshold = float(os.environ.get("OPENOB_LCD_VU_SNAP_THRESHOLD", "0.02"))

    last_bottom = ""
    last_bottom_update_ts = 0.0
    vu_timeout_s = float(os.environ.get("OPENOB_LCD_VU_TIMEOUT_S", "5.0"))

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

            # Periodic host health checks — update host_alert and host_alert_msg if issues seen
            if now >= next_host_check:
                next_host_check = now + host_check_s
                try:
                    ok, msg = check_hosts_status(encoder_ip, redis_host, gateway_ip if gateway_ip else None, timeout_s=ping_timeout_s, logger=logger)
                except Exception:
                    ok, msg = False, "HOSTS OFF"
                prev_alert = host_alert
                host_alert = not ok
                host_alert_msg = msg if host_alert else ""
                if logger and logger.isEnabledFor(logging.DEBUG) and host_alert != prev_alert:
                    logger.debug("Host alert changed: %s -> %s (%s)", prev_alert, host_alert, host_alert_msg)

            # If any host alert is active, override the top line to show the alert
            if host_alert:
                top = host_alert_msg

            # Periodic GPIO ping check (controls external indicator) — check less frequently than VU poll if desired
            if now >= last_gpio_check + gpio_check_s:
                last_gpio_check = now
                try:
                    ping_ok = check_consecutive_pings(encoder_ip, count=gpio_ping_count, timeout_s=ping_timeout_s, logger=logger)
                except Exception:
                    ping_ok = False
                # Only cut the relay (set to 0) when the encoder is unreachable. Do not auto-set it to 1 when reachable;
                # preserve whatever state is currently set (initial state remains as configured at startup).
                if not ping_ok:
                    desired_state = 0
                    if current_gpio_state is None or desired_state != current_gpio_state:
                        try:
                            subprocess.run(["gpio", "-g", "write", str(gpio_pin), "0"], check=True)
                            current_gpio_state = 0
                            if logger:
                                logger.info("Cut GPIO %d to 0 (encoder unreachable)", gpio_pin)
                        except Exception:
                            if logger:
                                logger.exception("Failed to write GPIO pin %d", gpio_pin)
                else:
                    # Encoder reachable — do not change the relay state; just log the observation.
                    if logger and logger.isEnabledFor(logging.DEBUG):
                        logger.debug("GPIO ping check to %s -> %s (encoder reachable); preserving state=%s", encoder_ip, ping_ok, current_gpio_state)

            # Poll Redis at a controlled rate to avoid hammering the server
            if client is not None and now >= last_vu_fetch + redis_poll_s:
                last_vu_fetch = now
                # Allow explicit key override like 'openob:transmission:vu:rx'
                fetch_key = vu_key_override if vu_key_override else vu_link_name
                vu = _fetch_rx_vu(client, fetch_key, direction=vu_direction, logger=logger)
                if logger and logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Fetched VU raw object: %r", vu)

                if vu is None:
                    target_left = 0.0
                    target_right = 0.0
                    if logger and logger.isEnabledFor(logging.DEBUG):
                        logger.debug("No VU data found -> targets set to 0.0")

                    # If VU is missing, try to discover correct link_name in Redis
                    if client is not None and now >= next_discover:
                        discovered = _discover_vu_link_name(client, logger=None)
                        if discovered and discovered != vu_link_name:
                            vu_link_name = discovered
                            if logger and logger.isEnabledFor(logging.DEBUG):
                                logger.debug("Discovered alternate VU key, switching link_name to %s", vu_link_name)
                        next_discover = now + max(1.0, discover_every_s)
                else:
                    # Log raw values from Redis for diagnosis
                    if logger and logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "Raw Redis values: left_db=%.3f right_db=%.3f updated_ts=%r source=%s",
                            vu.left_db,
                            vu.right_db,
                            vu.updated_ts,
                            vu.source,
                        )

                    # If the VU data is very stale, drop quickly to zero for a responsive display
                    if vu.updated_ts is None or (now - vu.updated_ts > vu_stale_drop_s):
                        target_left = 0.0
                        target_right = 0.0
                        if logger and logger.isEnabledFor(logging.DEBUG):
                            logger.debug("VU data stale (updated_ts=%r, now=%.3f) -> targets set to 0.0", vu.updated_ts, now)
                    else:
                        target_left = _db_to_norm_scaled(
                            vu.left_db,
                            min_db=vu_min_db,
                            gamma=vu_gamma,
                            headroom_db=vu_headroom_db,
                        )
                        target_right = _db_to_norm_scaled(
                            vu.right_db,
                            min_db=vu_min_db,
                            gamma=vu_gamma,
                            headroom_db=vu_headroom_db,
                        )

                        # Apply sensitivity multiplier and clamp to [0,1]
                        target_left = max(0.0, min(1.0, target_left * vu_sensitivity))
                        target_right = max(0.0, min(1.0, target_right * vu_sensitivity))

                        if logger and logger.isEnabledFor(logging.DEBUG):
                            segs_l = int(target_left * 7)
                            segs_r = int(target_right * 7)
                            logger.debug(
                                "Computed targets from Redis: target_left=%.4f target_right=%.4f (from left_db=%.3f right_db=%.3f, sens=%.2f) -> segments=(%d,%d)",
                                target_left,
                                target_right,
                                vu.left_db,
                                vu.right_db,
                                vu_sensitivity,
                                segs_l,
                                segs_r,
                            )

                        # Silence detection: if both targets are below threshold for N consecutive polls,
                        # treat as silence and force targets to zero to avoid showing low noise as activity.
                        if target_left <= vu_silence_target and target_right <= vu_silence_target:
                            vu_silence_counter += 1
                            if logger and logger.isEnabledFor(logging.DEBUG):
                                logger.debug("Low-level VU detected (%.4f, %.4f) -> silence_counter=%d", target_left, target_right, vu_silence_counter)
                        else:
                            if vu_silence_counter > 0:
                                if logger and logger.isEnabledFor(logging.DEBUG):
                                    logger.debug("VU above silence threshold, resetting silence_counter (was=%d)", vu_silence_counter)
                            vu_silence_counter = 0

                        if vu_silence_counter >= vu_silence_samples:
                            if logger and logger.isEnabledFor(logging.DEBUG):
                                logger.debug("Silence detected (counter=%d >= %d) -> forcing targets to 0", vu_silence_counter, vu_silence_samples)
                            target_left = 0.0
                            target_right = 0.0
                            vu_silence_counter = vu_silence_samples  # clamp

            # Smooth toward the target to make motion look natural and avoid flicker
            # Using asymmetric attack/release: faster release (drop) than attack (rise)
            try:
                alpha_attack = 1.0 - math.exp(-refresh_s / max(1e-6, vu_smooth_tau))
                alpha_release = 1.0 - math.exp(-refresh_s / max(1e-6, vu_release_tau))
            except Exception:
                alpha_attack = alpha_release = 1.0

            old_disp_left = disp_left
            old_disp_right = disp_right

            # Snap to zero if enabled and target is zero (makes pause appear immediate)
            if vu_snap_to_zero:
                if target_left == 0.0 and disp_left > vu_snap_threshold:
                    if logger and logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Snapping left display from %.4f to 0.0 (snap_to_zero)", disp_left)
                    disp_left = 0.0
                if target_right == 0.0 and disp_right > vu_snap_threshold:
                    if logger and logger.isEnabledFor(logging.DEBUG):
                        logger.debug("Snapping right display from %.4f to 0.0 (snap_to_zero)", disp_right)
                    disp_right = 0.0

            # Otherwise apply asymmetric smoothing per channel
            if target_left > disp_left:
                disp_left += (target_left - disp_left) * alpha_attack
            else:
                disp_left += (target_left - disp_left) * alpha_release

            if target_right > disp_right:
                disp_right += (target_right - disp_right) * alpha_attack
            else:
                disp_right += (target_right - disp_right) * alpha_release

            if logger and logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "alpha_a=%.4f alpha_r=%.4f old_disp=(%.4f,%.4f) target=(%.4f,%.4f) new_disp=(%.4f,%.4f)",
                    alpha_attack,
                    alpha_release,
                    old_disp_left,
                    old_disp_right,
                    target_left,
                    target_right,
                    disp_left,
                    disp_right,
                )
            # Render and update LCD only when changed (reduces writes) but keep fast responsiveness
            bottom = render_rx_bar(disp_left, disp_right)
            if bottom != last_bottom:
                if logger and logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Bottom changed, updating LCD bottom=%r", bottom)
                display.lcd_display_string(_fit_lcd(bottom), 2)
                last_bottom = bottom
                last_bottom_update_ts = now

            # Update top line always, bottom line only when changed
            display.lcd_display_string(_fit_lcd(top), 1)
            sleep(refresh_s)

    except KeyboardInterrupt:
        display.lcd_display_string(_fit_lcd("Borrando"), 1)
        display.lcd_display_string(_fit_lcd(""), 2)
        sleep(0.5)
        display.lcd_clear()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
