from machine import Pin, I2C, PWM, reset
import time
import socket
import network
import ntptime
import secrets
import json

if getattr(secrets, "SENSOR_TYPE", "CCS811") == "ENS160":
    from ens160_bme280 import BME280, ENS160 as GasSensor
    GAS_ADDR = 0x52
else:
    from wpse342 import BME280, CCS811 as GasSensor
    GAS_ADDR = 0x5B

SDA = 21
SCL = 22
BME_ADDR = 0x77

FAN_PIN  = 18
FAN_FREQ = 25_000        # Hz, Intel 4-pin PWM spec
FAN_DUTY = 50            # percent (0–100)

fan = PWM(Pin(FAN_PIN), freq=FAN_FREQ)
fan.duty_u16(int(65535 * FAN_DUTY / 100))
print("fan: GPIO%d  %d%%  %dHz" % (FAN_PIN, FAN_DUTY, FAN_FREQ))

SAMPLE_MS = 2000
HTTP_PORT = getattr(secrets, "HTTP_PORT", 8000)

# --- WLAN ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

if not wlan.isconnected():
    wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PSK)
    for _ in range(60):
        if wlan.isconnected():
            break
        time.sleep(0.5)

# --- NTP ---
ntptime.host = getattr(secrets, "NTP_HOST", "pool.ntp.org")
try:
    ntptime.settime()
except Exception:
    pass

i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=100_000)

# Fail-fast visibility
addrs = i2c.scan()
print("I2C:", [hex(a) for a in addrs])

bme = BME280(i2c, addr=BME_ADDR)
gas = GasSensor(i2c, addr=GAS_ADDR)

BASELINE_FILE    = "ccs811_baseline.json"
BASELINE_SAVE_MS = 24 * 3600 * 1000  # save window 24h

# load baseline (CCS811 only — ENS160 manages baseline on-chip, set_baseline() is a no-op)
try:
    with open(BASELINE_FILE, "r") as f:
        gas.set_baseline(json.load(f)["bl"])
        print("baseline: loaded")
except:
    print("baseline: none found, fresh start")

last_baseline_save  = time.ticks_ms()
eco2_min_seen   = None  # lowest eco2 observed in current 24h window
baseline_at_min = None  # baseline captured at that minimum moment

# Smoothing buffer for env compensation passed to gas sensor.
# A 5-sample moving average prevents abrupt ENV_DATA updates during
# rapid temperature/humidity changes (e.g. ventilation).
ENV_SMOOTH_N  = 5
_env_t_buf  = []
_env_rh_buf = []

def smooth_env(t, rh):
    """Return smoothed (t, rh) using a fixed-size moving average buffer."""
    _env_t_buf.append(t)
    _env_rh_buf.append(rh)
    if len(_env_t_buf) > ENV_SMOOTH_N:
        _env_t_buf.pop(0)
        _env_rh_buf.pop(0)
    return sum(_env_t_buf) / len(_env_t_buf), sum(_env_rh_buf) / len(_env_rh_buf)

latest = {
    "ms": 0,
    "ts": None,   # Unix epoch seconds (1970) if time is set
    "t": None,
    "rh": None,
    "p": None,
    "eco2": None,
    "tvoc": None,
}

def now_unix_or_none():
    # MicroPython time.time() is typically seconds since 2000-01-01 on ESP32
    # Convert to Unix epoch (1970) by adding 946684800
    try:
        ts = int(time.time()) + 946684800
        # sanity: require >= 2020-01-01
        return ts if ts >= 1577836800 else None
    except Exception:
        return None

def f_or_nan(v, fmt="%.2f"):
    if v is None:
        return "NaN"
    if isinstance(v, float):
        return fmt % v
    return str(v)

def build_metrics():
    # Optional: RSSI
    rssi = None
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            # some ports support wlan.status('rssi')
            try:
                rssi = wlan.status("rssi")
            except Exception:
                rssi = None
    except Exception:
        rssi = None

    uptime = time.ticks_ms() / 1000.0

    lines = []
    lines.append("# HELP esp32_uptime_seconds Uptime seconds since boot")
    lines.append("# TYPE esp32_uptime_seconds gauge")
    lines.append("esp32_uptime_seconds %s" % f_or_nan(uptime, "%.3f"))

    lines.append("# HELP esp32_unix_time_seconds Device unix time if available (UTC)")
    lines.append("# TYPE esp32_unix_time_seconds gauge")
    lines.append("esp32_unix_time_seconds %s" % ("NaN" if latest["ts"] is None else str(latest["ts"])))

    lines.append("# HELP esp32_temperature_celsius Temperature from BME280")
    lines.append("# TYPE esp32_temperature_celsius gauge")
    lines.append("esp32_temperature_celsius %s" % f_or_nan(latest["t"], "%.2f"))

    lines.append("# HELP esp32_humidity_percent Relative humidity from BME280")
    lines.append("# TYPE esp32_humidity_percent gauge")
    lines.append("esp32_humidity_percent %s" % f_or_nan(latest["rh"], "%.2f"))

    lines.append("# HELP esp32_pressure_hpa Pressure from BME280")
    lines.append("# TYPE esp32_pressure_hpa gauge")
    lines.append("esp32_pressure_hpa %s" % f_or_nan(latest["p"], "%.2f"))

    lines.append("# HELP esp32_eco2_ppm eCO2 from gas sensor (ppm, equivalent)")
    lines.append("# TYPE esp32_eco2_ppm gauge")
    lines.append("esp32_eco2_ppm %s" % f_or_nan(latest["eco2"]))

    lines.append("# HELP esp32_tvoc_ppb TVOC from gas sensor (ppb)")
    lines.append("# TYPE esp32_tvoc_ppb gauge")
    lines.append("esp32_tvoc_ppb %s" % f_or_nan(latest["tvoc"]))

    if rssi is not None:
        lines.append("# HELP esp32_wifi_rssi_dbm WiFi RSSI in dBm (if available)")
        lines.append("# TYPE esp32_wifi_rssi_dbm gauge")
        lines.append("esp32_wifi_rssi_dbm %s" % str(rssi))

    return "\n".join(lines) + "\n"

def build_baseline():
    bl_saved = None
    try:
        with open(BASELINE_FILE, "r") as f:
            bl_saved = json.load(f).get("bl")
    except:
        pass
    eco2_min = "null" if eco2_min_seen is None else str(eco2_min_seen)
    bl_cur   = "null" if baseline_at_min is None else str(baseline_at_min)
    bl_file  = "null" if bl_saved is None else str(bl_saved)
    return ('{"bl_saved":%s,"bl_current_window":%s,"eco2_min_window":%s}\n'
            % (bl_file, bl_cur, eco2_min))

def build_json():
    ts = "null" if latest["ts"] is None else str(latest["ts"])
    t  = "null" if latest["t"] is None else ("%.2f" % latest["t"])
    rh = "null" if latest["rh"] is None else ("%.2f" % latest["rh"])
    p  = "null" if latest["p"] is None else ("%.2f" % latest["p"])
    eco2 = "null" if latest["eco2"] is None else str(latest["eco2"])
    tvoc = "null" if latest["tvoc"] is None else str(latest["tvoc"])
    return ('{"ts":%s,"ms":%d,"t":%s,"rh":%s,"p":%s,"eco2":%s,"tvoc":%s}\n'
            % (ts, latest["ms"], t, rh, p, eco2, tvoc))

UPDATE_TOKEN = getattr(secrets, "UPDATE_TOKEN", None)
UPDATE_MAX_BYTES = 65536  # 64 KB

def _content_length(req):
    for line in req.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            try:
                return int(line.split(b":", 1)[1].strip())
            except Exception:
                pass
    return 0

def _recv_body(cl, req, length):
    idx = req.find(b"\r\n\r\n")
    body = req[idx + 4:] if idx >= 0 else b""
    cl.settimeout(10)
    while len(body) < length:
        try:
            chunk = cl.recv(min(512, length - len(body)))
        except OSError:
            break
        if not chunk:
            break
        body += chunk
    return body

def http_reply(cl, status, ctype, body):
    cl.send(("HTTP/1.1 %s\r\n" % status).encode())
    cl.send(("Content-Type: %s\r\n" % ctype).encode())
    cl.send(("Content-Length: %d\r\n" % len(body)).encode())
    cl.send(b"Connection: close\r\n\r\n")
    cl.send(body)

# HTTP server
srv = socket.socket()
try:
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
except Exception:
    pass
srv.bind(("0.0.0.0", HTTP_PORT))
srv.listen(2)
srv.settimeout(0)

print("http: listening on :%d (/metrics, /json)" % HTTP_PORT)

last_sample = time.ticks_ms()

while True:
    # sample sensors
    now = time.ticks_ms()
    if time.ticks_diff(now, last_sample) >= SAMPLE_MS:
        last_sample = now

        latest["ms"] = now
        latest["ts"] = now_unix_or_none()

        t, rh, p = bme.read()
        latest["t"], latest["rh"], latest["p"] = t, rh, p

        # env compensation (smoothed temp + humidity passed to gas sensor)
        try:
            t_s, rh_s = smooth_env(t, rh)
            gas.set_env(t_s, rh_s)
        except Exception:
            pass

        if gas.ready():
            eco2, tvoc, status, err = gas.read()
            if err == 0:
                latest["eco2"], latest["tvoc"] = eco2, tvoc
                # minimum tracking: capture baseline at the cleanest moment seen
                # ENS160: get_baseline() returns None, so baseline_at_min stays None
                # and the JSON save is skipped — ENS160 manages baseline on-chip.
                if eco2_min_seen is None or eco2 < eco2_min_seen:
                    eco2_min_seen = eco2
                    try:
                        baseline_at_min = gas.get_baseline()
                    except:
                        pass
            else:
                latest["eco2"], latest["tvoc"] = None, None

        # Baseline save — store the baseline captured at the 24h eco2 minimum.
        # Only overwrite the saved baseline if the window minimum is plausible
        # (< 800 ppm), to avoid replacing a known-good baseline with a worse one.
        if time.ticks_diff(now, last_baseline_save) >= BASELINE_SAVE_MS:
            last_baseline_save = now
            if baseline_at_min is not None and eco2_min_seen is not None and eco2_min_seen < 800:
                try:
                    with open(BASELINE_FILE, "w") as f:
                        json.dump({"bl": baseline_at_min}, f)
                    print("baseline: saved %d at eco2_min=%d ppm" % (baseline_at_min, eco2_min_seen))
                except:
                    pass
            elif baseline_at_min is None:
                print("baseline: skipped (no valid eco2 reading in window)")
            else:
                print("baseline: kept old (eco2_min=%d >= 800 ppm, window too polluted)" % eco2_min_seen)
            eco2_min_seen   = None
            baseline_at_min = None


        # debugging/logging
        print(build_json().strip())

    # serve HTTP
    try:
        cl, addr = srv.accept()
    except OSError:
        cl = None

    if cl:
        try:
            cl.settimeout(2)
            req = cl.recv(512)
            # very small parser: GET|POST /path HTTP/1.1
            path = b"/"
            if req.startswith(b"GET ") or req.startswith(b"POST "):
                parts = req.split(b" ")
                if len(parts) >= 2:
                    path = parts[1]

            if path == b"/metrics":
                body = build_metrics().encode()
                http_reply(cl, "200 OK", "text/plain; version=0.0.4; charset=utf-8", body)
            elif path == b"/json":
                body = build_json().encode()
                http_reply(cl, "200 OK", "application/json; charset=utf-8", body)
            elif path == b"/baseline":
                body = build_baseline().encode()
                http_reply(cl, "200 OK", "application/json; charset=utf-8", body)
            elif path.startswith(b"/update"):
                # Minimal auth: check ?token= query param against secrets.UPDATE_TOKEN
                token_ok = UPDATE_TOKEN is None
                if not token_ok and b"?" in path:
                    for p in path.split(b"?", 1)[1].split(b"&"):
                        if p.startswith(b"token=") and p[6:].decode() == UPDATE_TOKEN:
                            token_ok = True
                if not token_ok:
                    http_reply(cl, "403 Forbidden", "text/plain; charset=utf-8", b"forbidden\n")
                else:
                    fname = "main.py"
                    if b"?" in path:
                        for p in path.split(b"?", 1)[1].split(b"&"):
                            if p.startswith(b"file="):
                                fname = p[5:].decode()
                    clen = _content_length(req)
                    if clen == 0 or clen > UPDATE_MAX_BYTES:
                        http_reply(cl, "400 Bad Request", "text/plain; charset=utf-8", b"bad content-length\n")
                    else:
                        body = _recv_body(cl, req, clen)
                        if len(body) < clen:
                            http_reply(cl, "400 Bad Request", "text/plain; charset=utf-8", b"incomplete body\n")
                        else:
                            try:
                                with open(fname, "wb") as f:
                                    f.write(body)
                                msg = ("updated %s (%d bytes), rebooting\n" % (fname, len(body))).encode()
                                http_reply(cl, "200 OK", "text/plain; charset=utf-8", msg)
                                try:
                                    cl.close()
                                except Exception:
                                    pass
                                time.sleep_ms(200)
                                reset()
                            except Exception as e:
                                http_reply(cl, "500 Internal Server Error", "text/plain; charset=utf-8", str(e).encode())
            else:
                body = b"not found\n"
                http_reply(cl, "404 Not Found", "text/plain; charset=utf-8", body)
        except Exception:
            pass
        try:
            cl.close()
        except Exception:
            pass

    time.sleep_ms(20)
