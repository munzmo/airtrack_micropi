from machine import Pin, I2C, PWM
import time
import socket
import network
import ntptime
import secrets
import json

from wpse342 import BME280, CCS811

SDA = 21
SCL = 22
BME_ADDR = 0x77
CCS_ADDR = 0x5B

FAN_PIN  = 18
FAN_FREQ = 25_000        # Hz, Intel 4-pin PWM spec
FAN_DUTY = 20            # percent (0–100)

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
ccs = CCS811(i2c, addr=CCS_ADDR)

BASELINE_FILE = "ccs811_baseline.json"
BASELINE_SAVE_MS = 12 * 3600 * 1000  # save all 12h

# load baseline
try:
    with open(BASELINE_FILE, "r") as f:
        ccs.set_baseline(json.load(f)["bl"])
        print("baseline: loaded")
except:
    print("baseline: none found, fresh start")

last_baseline_save = time.ticks_ms()

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

    lines.append("# HELP esp32_eco2_ppm eCO2 from CCS811 (ppm, equivalent)")
    lines.append("# TYPE esp32_eco2_ppm gauge")
    lines.append("esp32_eco2_ppm %s" % f_or_nan(latest["eco2"]))

    lines.append("# HELP esp32_tvoc_ppb TVOC from CCS811 (ppb)")
    lines.append("# TYPE esp32_tvoc_ppb gauge")
    lines.append("esp32_tvoc_ppb %s" % f_or_nan(latest["tvoc"]))

    if rssi is not None:
        lines.append("# HELP esp32_wifi_rssi_dbm WiFi RSSI in dBm (if available)")
        lines.append("# TYPE esp32_wifi_rssi_dbm gauge")
        lines.append("esp32_wifi_rssi_dbm %s" % str(rssi))

    return "\n".join(lines) + "\n"

def build_json():
    ts = "null" if latest["ts"] is None else str(latest["ts"])
    t  = "null" if latest["t"] is None else ("%.2f" % latest["t"])
    rh = "null" if latest["rh"] is None else ("%.2f" % latest["rh"])
    p  = "null" if latest["p"] is None else ("%.2f" % latest["p"])
    eco2 = "null" if latest["eco2"] is None else str(latest["eco2"])
    tvoc = "null" if latest["tvoc"] is None else str(latest["tvoc"])
    return ('{"ts":%s,"ms":%d,"t":%s,"rh":%s,"p":%s,"eco2":%s,"tvoc":%s}\n'
            % (ts, latest["ms"], t, rh, p, eco2, tvoc))

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

        # env compensation for CCS811
        try:
            ccs.set_env(t, rh)
        except Exception:
            pass

        if ccs.ready():
            eco2, tvoc, status, err = ccs.read()
            if err == 0:
                latest["eco2"], latest["tvoc"] = eco2, tvoc
            else:
                latest["eco2"], latest["tvoc"] = None, None
        
        # Baseline periodically save
        if time.ticks_diff(now, last_baseline_save) >= BASELINE_SAVE_MS:
            try:
                bl = ccs.get_baseline()
                with open(BASELINE_FILE, "w") as f:
                    json.dump({"bl": bl}, f)
                print("baseline: saved", bl)
                last_baseline_save = now
            except:
                pass


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
            # very small parser: GET /path HTTP/1.1
            path = b"/"
            if req.startswith(b"GET "):
                parts = req.split(b" ")
                if len(parts) >= 2:
                    path = parts[1]

            if path == b"/metrics":
                body = build_metrics().encode()
                http_reply(cl, "200 OK", "text/plain; version=0.0.4; charset=utf-8", body)
            elif path == b"/json":
                body = build_json().encode()
                http_reply(cl, "200 OK", "application/json; charset=utf-8", body)
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
