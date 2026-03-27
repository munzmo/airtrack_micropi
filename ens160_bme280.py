"""
ENS160 + BME280 driver for MicroPython (ESP32).
Exposes the same interface as wpse342.py so main.py works unchanged.

ENS160 I2C address: 0x53 (ADDR pin floating/high, default on SparkFun board)
                   0x52 if ADDR pin is pulled to GND
BME280 I2C address: 0x77 (same as WPSE342)
"""

# -- BME280 ------------------------------------------------------------------------
# Identical chip, identical driver - re-exported from wpse342.py.
from wpse342 import BME280  # noqa: F401


# -- ENS160 ------------------------------------------------------------------------
class ENS160:
    # Registers
    _PART_ID   = 0x00  # 2 bytes LE, expected 0x0160
    _OPMODE    = 0x10  # 1 byte: 0x00=DEEP_SLEEP, 0x01=IDLE, 0x02=STANDARD
    _CONFIG    = 0x11
    _COMMAND   = 0x12
    _TEMP_IN   = 0x13  # 2 bytes LE: Kelvin * 64
    _RH_IN     = 0x15  # 2 bytes LE: %RH * 512
    _STATUS    = 0x20  # bit1=NEWDAT, bits4:2=VALIDITY
    _DATA_AQI  = 0x21  # 1 byte, AQI-UBA 1–5
    _DATA_TVOC = 0x22  # 2 bytes LE, ppb
    _DATA_ECO2 = 0x24  # 2 bytes LE, ppm

    # VALIDITY field values (STATUS bits 4:2)
    _VALIDITY_NORMAL  = 0  # normal operation, data valid
    _VALIDITY_WARMUP  = 1  # warm-up (~3 min after power-on)
    _VALIDITY_STARTUP = 2  # initial start-up (~1 h after first power-on)
    _VALIDITY_INVALID = 3  # invalid output

    def __init__(self, i2c, addr=0x52):
        self._i2c = i2c
        self._addr = addr
        self._aqi = None
        # Start in STANDARD mode (1 s sampling)
        self._write1(self._OPMODE, 0x02)

    def _write1(self, reg, val):
        self._i2c.writeto_mem(self._addr, reg, bytes([val]))

    def _write2(self, reg, val16):
        self._i2c.writeto_mem(self._addr, reg,
                              bytes([val16 & 0xFF, (val16 >> 8) & 0xFF]))

    def _read(self, reg, n=1):
        return self._i2c.readfrom_mem(self._addr, reg, n)

    # -- public interface ------------------------------------------------------

    def ready(self):
        """Return True when a new measurement is available."""
        status = self._read(self._STATUS)[0]
        return bool(status & 0x02)  # NEWDAT bit

    def read(self):
        """
        Return (eco2_ppm, tvoc_ppb, status_byte, err).
        err=0: valid data.  err=1: invalid (warm-up, start-up, or error).
        """
        status = self._read(self._STATUS)[0]
        validity = (status >> 2) & 0x07

        if validity == ENS160._VALIDITY_INVALID:
            return 0, 0, status, 1

        eco2_b = self._read(self._DATA_ECO2, 2)
        tvoc_b = self._read(self._DATA_TVOC, 2)
        eco2 = eco2_b[0] | (eco2_b[1] << 8)
        tvoc = tvoc_b[0] | (tvoc_b[1] << 8)
        self._aqi = self._read(self._DATA_AQI)[0]

        # err=0 also during warm-up/startup: data is preliminary but usable
        return eco2, tvoc, status, 0

    def get_aqi(self):
        """Return AQI-UBA (1=excellent .. 5=very poor), or None if not yet read."""
        return self._aqi

    def set_env(self, temp_c, rh):
        """Pass current temperature and humidity for internal compensation."""
        t_raw  = int((temp_c + 273.15) * 64)
        rh_raw = int(rh * 512)
        self._write2(self._TEMP_IN, t_raw)
        self._write2(self._RH_IN,   rh_raw)

    def get_baseline(self):
        """
        ENS160 manages its baseline autonomously in non-volatile memory.
        Returns None so that main.py skips the external JSON baseline save.
        """
        return None

    def set_baseline(self, bl):
        """No-op — ENS160 handles baseline internally."""
        pass
