"""
WPSE342 driver for MicroPython (ESP32).
Exposes the same interface as ens160_bme280.py so main.py works unchanged.

BME280 I2C address: 0x77
CCS811 I2C address: 0x5B
"""

import time


def s16(v):
    """Convert unsigned 16-bit value to signed."""
    return v - 65536 if v > 32767 else v


# -- BME280 -------------------------------------------------------------------------------------
class BME280:
    # Registers
    _REG_CAL1   = 0x88  # 26 bytes: T1–T3, P1–P9 calibration
    _REG_H1     = 0xA1  # 1 byte:  H1 calibration
    _REG_CAL2   = 0xE1  # 7 bytes: H2–H6 calibration
    _REG_CTRL_H = 0xF2  # humidity oversampling
    _REG_CTRL_M = 0xF4  # temp/pressure oversampling + mode
    _REG_CONFIG = 0xF5  # standby time + filter
    _REG_DATA   = 0xF7  # 8 bytes: press[2:0], temp[2:0], hum[1:0]

    def __init__(self, i2c, addr=0x77):
        self.i2c  = i2c
        self.addr = addr
        self._load_cal()
        self._w8(self._REG_CTRL_H, 0x01)   # humidity oversampling x1
        self._w8(self._REG_CTRL_M, 0x27)   # temp/pressure oversampling x1, normal mode
        self._w8(self._REG_CONFIG, 0xA0)   # standby 1000 ms
        time.sleep_ms(20)

    def _rN(self, reg, n):
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _r8(self, reg):
        return self._rN(reg, 1)[0]

    def _w8(self, reg, v):
        self.i2c.writeto_mem(self.addr, reg, bytes([v]))

    def _load_cal(self):
        """Read factory calibration coefficients from OTP registers."""
        cal1 = self._rN(self._REG_CAL1, 26)
        # Temperature coefficients (T1 unsigned, T2/T3 signed)
        self.dig_T1 = cal1[0] | (cal1[1] << 8)
        self.dig_T2 = s16(cal1[2] | (cal1[3] << 8))
        self.dig_T3 = s16(cal1[4] | (cal1[5] << 8))
        # Pressure coefficients (P1 unsigned, P2–P9 signed)
        self.dig_P1 = cal1[6]  | (cal1[7]  << 8)
        self.dig_P2 = s16(cal1[8]  | (cal1[9]  << 8))
        self.dig_P3 = s16(cal1[10] | (cal1[11] << 8))
        self.dig_P4 = s16(cal1[12] | (cal1[13] << 8))
        self.dig_P5 = s16(cal1[14] | (cal1[15] << 8))
        self.dig_P6 = s16(cal1[16] | (cal1[17] << 8))
        self.dig_P7 = s16(cal1[18] | (cal1[19] << 8))
        self.dig_P8 = s16(cal1[20] | (cal1[21] << 8))
        self.dig_P9 = s16(cal1[22] | (cal1[23] << 8))
        # Humidity coefficients (split across two register banks)
        self.dig_H1 = self._r8(self._REG_H1)
        cal2 = self._rN(self._REG_CAL2, 7)
        self.dig_H2 = s16(cal2[0] | (cal2[1] << 8))
        self.dig_H3 = cal2[2]
        e4, e5, e6  = cal2[3], cal2[4], cal2[5]
        self.dig_H4 = s16((e4 << 4) | (e5 & 0x0F))
        self.dig_H5 = s16((e6 << 4) | (e5 >> 4))
        self.dig_H6 = cal2[6] if cal2[6] < 128 else cal2[6] - 256

    def read(self):
        """
        Return (temp_c, rh_percent, pressure_hpa).
        pressure_hpa is None if the compensation denominator is zero.
        Uses Bosch-supplied integer compensation formulas from the BME280 datasheet.
        """
        data  = self._rN(self._REG_DATA, 8)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        adc_h = (data[6] << 8)  |  data[7]

        # Temperature — also produces t_fine used by pressure and humidity
        var1   = (((adc_t >> 3) - (self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2   = (((((adc_t >> 4) - self.dig_T1) * ((adc_t >> 4) - self.dig_T1)) >> 12) * self.dig_T3) >> 14
        t_fine = var1 + var2
        temp_c = ((t_fine * 5 + 128) >> 8) / 100.0

        # Pressure
        var1 = t_fine - 128000
        var2 = var1 * var1 * self.dig_P6
        var2 = var2 + ((var1 * self.dig_P5) << 17)
        var2 = var2 + (self.dig_P4 << 35)
        var1 = ((var1 * var1 * self.dig_P3) >> 8) + ((var1 * self.dig_P2) << 12)
        var1 = (((1 << 47) + var1) * self.dig_P1) >> 33
        if var1 == 0:
            pres_hpa = None   # avoid division by zero
        else:
            p       = 1048576 - adc_p
            p       = (((p << 31) - var2) * 3125) // var1
            var1p   = (self.dig_P9 * (p >> 13) * (p >> 13)) >> 25
            var2p   = (self.dig_P8 * p) >> 19
            p       = ((p + var1p + var2p) >> 8) + (self.dig_P7 << 4)
            pres_hpa = (p / 256.0) / 100.0

        # Humidity
        h = t_fine - 76800
        h = (((((adc_h << 14) - (self.dig_H4 << 20) - (self.dig_H5 * h)) + 16384) >> 15) *
             (((((((h * self.dig_H6) >> 10) * (((h * self.dig_H3) >> 11) + 32768)) >> 10) + 2097152) * self.dig_H2 + 8192) >> 14))
        h = h - (((((h >> 15) * (h >> 15)) >> 7) * self.dig_H1) >> 4)
        h = max(0, min(h, 419430400))   # clamp to [0, 100%] in fixed-point
        rh = (h >> 12) / 1024.0

        return temp_c, rh, pres_hpa


# -- CCS811 ----------------------------------------------------------------------------------------
class CCS811:
    # Registers
    _REG_STATUS     = 0x00  # 1 byte: APP_VALID, FW_MODE, DATA_READY, ERROR
    _REG_MEAS_MODE  = 0x01  # 1 byte: drive mode + interrupt config
    _REG_ALG_RESULT = 0x02  # 8 bytes: eCO2[1:0], TVOC[1:0], STATUS, ERROR_ID, RAW[1:0]
    _REG_ENV_DATA   = 0x05  # 4 bytes: humidity[1:0], temperature[1:0] (compensation input)
    _REG_BASELINE   = 0x11  # 2 bytes: opaque 16-bit baseline value
    _REG_APP_START  = 0xF4  # write-only: switches chip from boot to application mode
    _REG_SW_RESET   = 0xFF  # write 0x11 0xE5 0x72 0x8A to reset

    def __init__(self, i2c, addr=0x5B):
        self.i2c  = i2c
        self.addr = addr
        # Cached diagnostic data — updated on every read()
        self._diag_current_ua = None  # heater current in µA (0–63)
        self._diag_adc_raw    = None  # ADC result, proportional to sensor resistance (0–1023)
        self._diag_status     = None  # STATUS byte
        self._diag_err_id     = None  # ERROR_ID byte
        # Full software reset (magic sequence required by datasheet)
        self.i2c.writeto_mem(self.addr, self._REG_SW_RESET,
                             bytes([0x11, 0xE5, 0x72, 0x8A]))
        time.sleep_ms(100)
        # Start application firmware if chip is in boot mode and app is valid
        st = self._r8(self._REG_STATUS)
        app_valid = (st & 0x10) != 0
        fw_mode   = (st & 0x80) != 0
        if (not fw_mode) and app_valid:
            self.i2c.writeto(self.addr, bytes([self._REG_APP_START]))
            time.sleep_ms(100)
        # Drive mode 1: constant measurement every 1 s
        self._w8(self._REG_MEAS_MODE, 0x10)
        time.sleep_ms(20)

    def _r8(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def _rN(self, reg, n):
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _w8(self, reg, v):
        self.i2c.writeto_mem(self.addr, reg, bytes([v]))

    # -- public interface ---------------------------------------------------------------

    def ready(self):
        """Return True when a new measurement is available (DATA_READY bit)."""
        return (self._r8(self._REG_STATUS) & 0x08) != 0

    def read(self):
        """
        Return (eco2_ppm, tvoc_ppb, status_byte, err).
        err=0: valid data.  err!=0: sensor-reported error code.
        """
        d      = self._rN(self._REG_ALG_RESULT, 8)
        eco2   = (d[0] << 8) | d[1]
        tvoc   = (d[2] << 8) | d[3]
        status = d[4]
        err    = d[5]
        # Cache raw sensor data for /diag endpoint
        # Bytes 6–7: RAW_DATA — bits[15:10] = heater current (µA), bits[9:0] = ADC result
        self._diag_current_ua = (d[6] >> 2) & 0x3F
        self._diag_adc_raw    = ((d[6] & 0x03) << 8) | d[7]
        self._diag_status     = status
        self._diag_err_id     = err
        return eco2, tvoc, status, err

    def set_env(self, temp_c, rh):
        """Pass current temperature and humidity for internal compensation."""
        # CCS811 encoding: value = quantity * 512, big-endian, +25°C offset for temperature.
        # Lower byte holds sub-0.5 fractional precision — zeroed here for simplicity since
        # BME280 at x1 oversampling does not provide better than ~0.5°C / ~0.5% RH resolution.
        hum     = int(rh * 512)            & 0xFF00
        tmp     = int((temp_c + 25) * 512) & 0xFF00
        payload = bytes([(hum >> 8) & 0xFF, hum & 0xFF,
                         (tmp >> 8) & 0xFF, tmp & 0xFF])
        self.i2c.writeto_mem(self.addr, self._REG_ENV_DATA, payload)

    def get_baseline(self):
        """
        Read the current internal 16-bit baseline value.
        Opaque chip-internal reference — not in ppm or any physical unit.
        Saved externally (ccs811_baseline.json) and restored on boot to
        preserve calibration across power cycles.
        """
        d = self._rN(self._REG_BASELINE, 2)
        return (d[0] << 8) | d[1]

    def set_baseline(self, baseline):
        """Restore a previously saved baseline value into the chip."""
        self.i2c.writeto_mem(self.addr, self._REG_BASELINE,
                             bytes([(baseline >> 8) & 0xFF, baseline & 0xFF]))
