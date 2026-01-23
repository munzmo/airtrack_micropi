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
mpremote connect /dev/ttyUSB0 fs cp main.py :main.py
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

esp32_json_temperature_celsius
- Temperature in Unit **°C** (BME280)

esp32_json_humidity_percent
- Relative humidity in **%**

esp32_json_pressure_hpa
- Barometric pressure in **hPa**

esp32_json_eco2_ppm
- eCO2 in ppm (CCS811)

esp32_json_tvoc_ppb
- TVOC in ppb (CCS811)

esp32_json_ts_seconds
- Unix-Timestamp from ESP32 (UTC)

esp32_json_uptime_ms
- Uptime since last boot (MS)

esp32_json_exporter_up
- 1 = last poll successful, 0 = Error

esp32_json_exporter_poll_seconds
- Duration of the last JSON poll in seconds

## Low-Frequency
These metrics come directly from the ESP32 /metrics.

esp32_uptime_seconds
- Uptime seit letztem Boot (Sekunden)

esp32_unix_time_seconds
- Unix-Zeit des ESP32 (UTC)

esp32_wifi_rssi_dbm
- WLAN-Signalstärke in dBm

