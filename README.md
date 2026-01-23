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
