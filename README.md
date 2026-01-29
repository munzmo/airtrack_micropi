# Open Source Air Tracking

A brief description of what this project does and who it's for


## Monitoring points wpse342
### Chip BME280
* **t**: Temperature in Unit **°C**
* **rh**: Relative humidity in **%**
* **p**: Barometric pressure in **hPa**

### Chip CCS811
* **eco2**: Equivalent CO₂ in Unit **ppm** (vom **CCS811**). 
  * Not a true CO₂ meter, but calculated from VOC signals.

* **tvoc**: Total Volatile Organic Compounds in **ppb** (vom **CCS811**)
  * Volatile organic compounds as a total value.

## Connect to board
REPL connect
```console
mpremote connect /dev/ttyUSB0 repl
```

## Copy local to board
### Copy to board
```console
mpremote connect /dev/ttyUSB0 fs put boot.py
mpremote connect /dev/ttyUSB0 fs put main.py
mpremote connect /dev/ttyUSB0 fs put secrets.py
mpremote connect /dev/ttyUSB0 fs put wpse342.py
mpremote connect /dev/ttyUSB0 fs put wpse342_read.py
```
### Reset board - like reset button
```console
mpremote connect /dev/ttyUSB0 reset
```

## Curl endpoints local network
### Metadata
```console
curl http://192.168.178.37:8000/metrics
```
### Sensor readings
```console
curl http://192.168.178.37:8000/json
```

# Available endpoints
The individual measuring points can be addressed via the sensors {sensor=“SENS01”}, e.g.,
```console
esp32_json_temperature_celsius{sensor="SENS01"}
```

## High-Frequency
Metrics are created by Endpoint /json and formatted by Exporter in Prometheus format.

- Temperature in Unit **°C** (BME280)
```console
esp32_json_temperature_celsius
```
- Relative humidity in **%**
```console
esp32_json_humidity_percent
```
- Barometric pressure in **hPa**
```console
esp32_json_pressure_hpa
```
- eCO2 in ppm (CCS811)
```console
esp32_json_eco2_ppm
```
- TVOC in ppb (CCS811)
```console
esp32_json_tvoc_ppb
```
- Unix-Timestamp from ESP32 (UTC)
```console
esp32_json_ts_seconds
```
- Uptime since last boot (MS)
```console
esp32_json_uptime_ms
```
- 1 = last poll successful, 0 = Error
```console
esp32_json_exporter_up
```
- Duration of the last JSON poll in seconds
```console
esp32_json_exporter_poll_seconds
```

## Low-Frequency
These metrics come directly from the ESP32 /metrics.

- Uptime seit letztem Boot (Sekunden)
```console
esp32_uptime_seconds
```
- Unix-Zeit des ESP32 (UTC)
```console
esp32_unix_time_seconds
```
- WLAN-Signalstärke in dBm
```console
esp32_wifi_rssi_dbm
```

# Add new sensors

## Extend for /json endpoints
### Extend docker-compose.yml
```console
services:
[...]
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
[...]
```

### Extend prometheus.yml
```console
global:
  scrape_interval: 15s

scrape_configs:
[...]
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

[...]        
```
## Extend for /metrics endpoints
### Extend prometheus.yml
```console
global:
  scrape_interval: 15s

scrape_configs:
[...]
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
      # drop high-freq from /json
      - source_labels: [__name__]
        regex: 'esp32_(temperature_celsius|humidity_percent|pressure_hpa|eco2_ppm|tvoc_ppb)'
        action: drop

[...]        
```

## Refactor Docker Container
Apply compose changes + remove old renamed containers
```console
docker compose up -d --build --remove-orphans
```
Reload Prometheus config
```console
docker exec -it prometheus_track kill -HUP 1
```
