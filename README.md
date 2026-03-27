# Open Source Air Tracking

A brief description of what this project does and who it's for

---

## Sensor Hardware

Two sensor board variants are supported. Both use the same `main.py` — the active variant is selected via `SENSOR_TYPE` in `secrets.py`.

| Sensor Board | Gas Sensor | Env Sensor | Used on |
|---|---|---|---|
| WPSE342 | CCS811 (I2C 0x5B) | BME280 (I2C 0x77) | SENS01, SENS02, SENS03 |
| SparkFun ENS160/BME280 | ENS160 (I2C 0x52) | BME280 (I2C 0x77) | SENS04 |

---

## WPSE342 (SENS01 / SENS02 / SENS03)

### Wiring

| Sensor Pin | Signal | ESP32 Pin |
|------------|--------|-----------|
| 3.3V | Power | 3.3V |
| GND  | Ground | GND |
| SDA  | I2C Data | GPIO21 |
| SCL  | I2C Clock | GPIO22 |

### Chip BME280
* **t**: Temperature in **°C**
* **rh**: Relative humidity in **%**
* **p**: Barometric pressure in **hPa**

### Chip CCS811
* **eco2**: Equivalent CO₂ in **ppm** — calculated from VOC signals, not a true CO₂ meter.
* **tvoc**: Total Volatile Organic Compounds in **ppb**

#### CCS811 Baseline auto-save
The code tracks the **lowest eCO2 value observed within each 24h window** and captures the corresponding baseline at that moment. Every 24h the best baseline of the window is written to flash and the window resets.

The saved baseline is only overwritten if the window minimum was **< 800 ppm**. If the entire window was too polluted (≥ 800 ppm), the previously saved baseline is kept.

#### Reset CCS811 baseline (clean start)
The baseline survives power cycles and file uploads. Delete it explicitly for a clean restart:
```console
mpremote connect /dev/ttyUSB0 rm :ccs811_baseline.json
mpremote connect /dev/ttyUSB0 reset
```
The sensor will recalibrate from scratch (~20–48h until stable readings).

#### Flash CCS811 firmware to v2.0.1 (one-time, optional)
Improves internal calibration algorithm. Intended for already burned-in sensors.
**DISCLAIMER: Risk of bricking is low (bootloader untouched), but flash at own risk.**

Full sequence — flash, update files, clean baseline, restart:
```console
# 1. Flash CCS811 firmware
mpremote connect /dev/ttyUSB0 cp ccs811_flash.py :ccs811_flash.py
mpremote connect /dev/ttyUSB0 run ccs811_flash.py

# 2. Upload firmware files
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 cp wpse342.py :wpse342.py

# 3. Delete baseline
mpremote connect /dev/ttyUSB0 rm :ccs811_baseline.json

# 4. Reset
mpremote connect /dev/ttyUSB0 reset
```

---

## SparkFun ENS160/BME280 (SENS04)

### Wiring

| Sensor Pin | Signal | ESP32 Pin |
|------------|--------|-----------|
| 3.3V | Power | 3.3V |
| GND  | Ground | GND |
| SDA  | I2C Data | GPIO21 |
| SCL  | I2C Clock | GPIO22 |
| ADDR | I2C address select | open/high (→ 0x53), GND (→ 0x52) |

### Chip BME280
Identical chip to WPSE342 — same measurements: **t** (°C), **rh** (%), **p** (hPa).

### Chip ENS160
* **eco2**: Equivalent CO₂ in **ppm**
* **tvoc**: Total Volatile Organic Compounds in **ppb**
* Baseline is managed **automatically on-chip** in non-volatile memory — no external JSON file needed.

---

## Fan — Noctua NF-A4x10 5V PWM

A 4-pin PWM fan is connected to the board for active airflow. RPM readout is not used.

### Wiring

| Fan Pin | Signal | ESP32 Pin |
|---------|--------|-----------|
| 1 (Black) | GND | GND |
| 2 (Red)   | +5V | VIN (5V) |
| 3 (Yellow)| RPM | — (not connected) |
| 4 (Blue)  | PWM | GPIO18 |

### Configuration

| Parameter | Value |
|-----------|-------|
| PWM frequency | 25 kHz (Intel 4-pin fan spec) |
| Duty cycle | 50% (fixed) |
| PWM logic level | 3.3V (compatible with Noctua fans) |

Configured in `main.py` via `FAN_PIN`, `FAN_FREQ`, `FAN_DUTY`.

---

## Board setup & deployment

### secrets.py — per-board configuration

Each board gets its own `secrets.py` on flash. Two template files are kept locally (both gitignored):

| Local file | `SENSOR_TYPE` | Deploy to |
|---|---|---|
| `secrets_ccs811.py` | `"CCS811"` | SENS01, SENS02, SENS03 |
| `secrets_ens160.py` | `"ENS160"` | SENS04 |

### Initial setup (USB)

```console
# SENS01 / SENS02 / SENS03  (CCS811)
mpremote connect /dev/ttyUSB0 cp secrets_ccs811.py :secrets.py
mpremote connect /dev/ttyUSB0 cp boot.py :boot.py
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 cp wpse342.py :wpse342.py
mpremote connect /dev/ttyUSB0 cp ccs811_diag.py :ccs811_diag.py
mpremote connect /dev/ttyUSB0 reset

# SENS04  (ENS160)
mpremote connect /dev/ttyUSB0 cp secrets_ens160.py :secrets.py
mpremote connect /dev/ttyUSB0 cp boot.py :boot.py
mpremote connect /dev/ttyUSB0 cp main.py :main.py
mpremote connect /dev/ttyUSB0 cp wpse342.py :wpse342.py
mpremote connect /dev/ttyUSB0 cp ens160_bme280.py :ens160_bme280.py
mpremote connect /dev/ttyUSB0 reset
```

### OTA update (WiFi, after initial setup)

Once a board is running, files can be pushed over the local network without USB. The board reboots automatically after a successful write.

```console
# Update main.py on a single board
curl -X POST http://192.168.178.37:8000/update?file=main.py \
     --data-binary @main.py

# Update any other file
curl -X POST http://192.168.178.37:8000/update?file=wpse342.py \
     --data-binary @wpse342.py
```

| Parameter | Description |
|-----------|-------------|
| `file` | Target filename on the board (default: `main.py`) |
| `token` | Required if `UPDATE_TOKEN` is set in `secrets.py` |

Maximum upload size: 64 KB.

#### Optional token protection
Add to `secrets.py` to require a token on every update request:
```python
UPDATE_TOKEN = "your-secret"
```
```console
curl -X POST "http://192.168.178.37:8000/update?file=main.py&token=your-secret" \
     --data-binary @main.py
```

### Other mpremote commands

```console
# REPL
mpremote connect /dev/ttyUSB0 repl

# Reset (like reset button)
mpremote connect /dev/ttyUSB0 reset
```

---

## HTTP endpoints

### Prometheus metrics
```console
curl http://192.168.178.37:8000/metrics
```

### Sensor readings (JSON)
```console
curl http://192.168.178.37:8000/json
```

### CCS811 diagnostics
```console
curl http://192.168.178.37:8000/diag | python3 -m json.tool
```
Returns a detailed JSON explaining the current sensor state. Only available on CCS811 boards (`SENSOR_TYPE = "CCS811"`).

```json
{
  "readings":         { "eco2_ppm": 411, "tvoc_ppb": 1 },
  "env_compensation": { "t_raw_c": 19.05, "rh_raw_pct": 47.34,
                        "t_smooth_c": 19.04, "rh_smooth_pct": 47.31,
                        "buffer_n": 5, "t_buf": [...], "rh_buf": [...] },
  "baseline":         { "current_chip": 44488, "saved_disk": 44488,
                        "eco2_min_window": 402, "baseline_at_min": 44488 },
  "raw_sensor":       { "current_ua": 14, "adc_raw": 287 },
  "status":           { "fw_mode": true, "app_valid": true,
                        "data_ready": true, "error": false, "raw": 152 },
  "error_id":         { "heater_supply": false, "heater_fault": false,
                        "max_resistance": false, "measmode_invalid": false,
                        "read_reg_invalid": false, "msg_invalid": false, "raw": 0 }
}
```

| Field | Description |
|-------|-------------|
| `readings.eco2_ppm` | Current eCO2 output (ppm) |
| `readings.tvoc_ppb` | Current TVOC output (ppb) |
| `env_compensation.t_raw_c` | Raw temperature from BME280 (°C) |
| `env_compensation.t_smooth_c` | Smoothed temperature actually sent to CCS811 (°C) |
| `env_compensation.rh_raw_pct` | Raw humidity from BME280 (%) |
| `env_compensation.rh_smooth_pct` | Smoothed humidity actually sent to CCS811 (%) |
| `env_compensation.t_buf` / `rh_buf` | Current moving average buffer (5 samples, 2s each) |
| `baseline.current_chip` | Baseline currently active in chip (opaque 16-bit value) |
| `baseline.saved_disk` | Baseline stored in `ccs811_baseline.json` |
| `baseline.eco2_min_window` | Lowest eCO2 seen in current 24h window (ppm) |
| `baseline.baseline_at_min` | Chip baseline captured at that minimum moment |
| `raw_sensor.current_ua` | Heater current through MOX element (µA, 0–63) |
| `raw_sensor.adc_raw` | ADC resistance reading (0–1023, higher = cleaner air) |
| `status.fw_mode` | `true` = application firmware running, `false` = bootloader |
| `status.data_ready` | `true` = new measurement available |
| `status.error` | `true` = error occurred, see `error_id` for details |
| `error_id.*` | Individual error flags decoded from ERROR_ID register |

### Baseline status
```console
curl http://192.168.178.37:8000/baseline
```
Returns:
```json
{"bl_saved": 12345, "bl_current_window": 12300, "eco2_min_window": 400}
```

| Field | Description |
|-------|-------------|
| `bl_saved` | Baseline stored in `ccs811_baseline.json` (CCS811 only, loaded on boot) |
| `bl_current_window` | Baseline captured at the eco2 minimum in the current 24h window |
| `eco2_min_window` | Lowest eCO2 (ppm) seen in the current 24h window |

> ENS160 boards: all three fields return `null` — baseline is managed on-chip.

### Delete baseline (remote reset)
Deletes `ccs811_baseline.json` from flash and reboots the board. The sensor starts fresh without a loaded baseline. Token required if `UPDATE_TOKEN` is set.

```console
curl "http://192.168.178.37:8000/delete-baseline?token=your-secret"
```

The board responds with `baseline deleted, rebooting` and restarts immediately. Use this when:
- The saved baseline is corrupted or from a bad session
- A clean recalibration from scratch is needed

> After reboot the sensor runs uncalibrated for 20 minutes (conditioning period), then ABC takes over. Expose the sensor to fresh air within the first 24h to ensure a good baseline is captured.

---

# Prometheus / Grafana

## Available metrics

Metrics are identical regardless of sensor variant. Individual boards are addressed via the `sensor` label:
```console
esp32_json_temperature_celsius{sensor="SENS01"}
```

### High-frequency (via `/json` exporter)

| Metric | Unit | Source |
|--------|------|--------|
| `esp32_json_temperature_celsius` | °C | BME280 |
| `esp32_json_humidity_percent` | % | BME280 |
| `esp32_json_pressure_hpa` | hPa | BME280 |
| `esp32_json_eco2_ppm` | ppm | CCS811 / ENS160 |
| `esp32_json_tvoc_ppb` | ppb | CCS811 / ENS160 |
| `esp32_json_ts_seconds` | Unix timestamp | ESP32 |
| `esp32_json_uptime_ms` | ms | ESP32 |
| `esp32_json_exporter_up` | 1 = ok, 0 = error | Exporter |
| `esp32_json_exporter_poll_seconds` | s | Exporter |

### Low-frequency (via `/metrics`)

| Metric | Unit |
|--------|------|
| `esp32_uptime_seconds` | s |
| `esp32_unix_time_seconds` | Unix timestamp |
| `esp32_wifi_rssi_dbm` | dBm |

## Add a new sensor board

### Extend docker-compose.yml
```yaml
esp32-json-exporter-sens01:
    build: ./esp32_json_exporter
    container_name: esp32-json-exporter-sens01
    environment:
      ESP32_JSON_URL: "http://192.168.178.37:8000/json"
      POLL_SECONDS: "3"
      LISTEN_PORT: "9105"
      HTTP_TIMEOUT: "1.5"
    restart: unless-stopped
    ports:
      - "9105:9105"
    networks:
      - proxy

esp32-json-exporter-sens02:
    build: ./esp32_json_exporter
    container_name: esp32-json-exporter-sens02
    environment:
      ESP32_JSON_URL: "http://192.168.178.38:8000/json"
      POLL_SECONDS: "3"
      LISTEN_PORT: "9106"
      HTTP_TIMEOUT: "1.5"
    restart: unless-stopped
    ports:
      - "9106:9106"
    networks:
      - proxy
```

### Extend prometheus.yml
```yaml
scrape_configs:
  - job_name: "esp32_json"
    scrape_interval: 3s
    scrape_timeout: 2s
    static_configs:
      - targets: ["192.168.178.29:9105"]
        labels:
          device: "esp32"
          endpoint: "json"
          sensor: "SENS01"
      - targets: ["192.168.178.29:9106"]
        labels:
          device: "esp32"
          endpoint: "json"
          sensor: "SENS02"
    relabel_configs:
      - source_labels: [sensor]
        target_label: instance

  - job_name: "esp32_metrics"
    scrape_interval: 5m
    scrape_timeout: 10s
    metrics_path: /metrics
    static_configs:
      - targets: ["192.168.178.37:8000"]
        labels:
          device: "esp32"
          endpoint: "metrics"
          sensor: "SENS01"
      - targets: ["192.168.178.38:8000"]
        labels:
          device: "esp32"
          endpoint: "metrics"
          sensor: "SENS02"
    relabel_configs:
      - source_labels: [sensor]
        target_label: instance
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'esp32_(temperature_celsius|humidity_percent|pressure_hpa|eco2_ppm|tvoc_ppb)'
        action: drop
```

### Apply changes

```console
# Rebuild containers
docker compose up -d --build --remove-orphans

# Reload Prometheus config
docker exec -it prometheus_track kill -HUP 1
```
