import time

def s16(v):
    return v - 65536 if v > 32767 else v

class BME280:
    def __init__(self, i2c, addr=0x77):
        self.i2c = i2c
        self.addr = addr
        self._load_cal()
        # hum x1
        self._w8(0xF2, 0x01)
        # temp/press x1, normal mode
        self._w8(0xF4, 0x27)
        # standby 1000ms
        self._w8(0xF5, 0xA0)
        time.sleep_ms(20)

    def _rN(self, reg, n):
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _r8(self, reg):
        return self._rN(reg, 1)[0]

    def _w8(self, reg, v):
        self.i2c.writeto_mem(self.addr, reg, bytes([v]))

    def _load_cal(self):
        cal1 = self._rN(0x88, 26)
        self.dig_T1 = cal1[0] | (cal1[1] << 8)
        self.dig_T2 = s16(cal1[2] | (cal1[3] << 8))
        self.dig_T3 = s16(cal1[4] | (cal1[5] << 8))

        self.dig_P1 = cal1[6] | (cal1[7] << 8)
        self.dig_P2 = s16(cal1[8] | (cal1[9] << 8))
        self.dig_P3 = s16(cal1[10] | (cal1[11] << 8))
        self.dig_P4 = s16(cal1[12] | (cal1[13] << 8))
        self.dig_P5 = s16(cal1[14] | (cal1[15] << 8))
        self.dig_P6 = s16(cal1[16] | (cal1[17] << 8))
        self.dig_P7 = s16(cal1[18] | (cal1[19] << 8))
        self.dig_P8 = s16(cal1[20] | (cal1[21] << 8))
        self.dig_P9 = s16(cal1[22] | (cal1[23] << 8))

        self.dig_H1 = self._r8(0xA1)
        cal2 = self._rN(0xE1, 7)
        self.dig_H2 = s16(cal2[0] | (cal2[1] << 8))
        self.dig_H3 = cal2[2]
        e4, e5, e6 = cal2[3], cal2[4], cal2[5]
        self.dig_H4 = s16((e4 << 4) | (e5 & 0x0F))
        self.dig_H5 = s16((e6 << 4) | (e5 >> 4))
        self.dig_H6 = cal2[6] if cal2[6] < 128 else cal2[6] - 256

    def read(self):
        data = self._rN(0xF7, 8)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        adc_h = (data[6] << 8) | data[7]

        # temp
        var1 = (((adc_t >> 3) - (self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2 = (((((adc_t >> 4) - self.dig_T1) * ((adc_t >> 4) - self.dig_T1)) >> 12) * self.dig_T3) >> 14
        t_fine = var1 + var2
        temp_c = ((t_fine * 5 + 128) >> 8) / 100.0

        # press
        var1 = t_fine - 128000
        var2 = var1 * var1 * self.dig_P6
        var2 = var2 + ((var1 * self.dig_P5) << 17)
        var2 = var2 + (self.dig_P4 << 35)
        var1 = ((var1 * var1 * self.dig_P3) >> 8) + ((var1 * self.dig_P2) << 12)
        var1 = (((1 << 47) + var1) * self.dig_P1) >> 33

        if var1 == 0:
            pres_hpa = None
        else:
            p = 1048576 - adc_p
            p = (((p << 31) - var2) * 3125) // var1
            var1p = (self.dig_P9 * (p >> 13) * (p >> 13)) >> 25
            var2p = (self.dig_P8 * p) >> 19
            p = ((p + var1p + var2p) >> 8) + (self.dig_P7 << 4)
            pres_hpa = (p / 256.0) / 100.0

        # hum
        h = t_fine - 76800
        h = (((((adc_h << 14) - (self.dig_H4 << 20) - (self.dig_H5 * h)) + 16384) >> 15) *
             (((((((h * self.dig_H6) >> 10) * (((h * self.dig_H3) >> 11) + 32768)) >> 10) + 2097152) * self.dig_H2 + 8192) >> 14))
        h = h - (((((h >> 15) * (h >> 15)) >> 7) * self.dig_H1) >> 4)
        h = 0 if h < 0 else h
        h = 419430400 if h > 419430400 else h
        rh = (h >> 12) / 1024.0

        return temp_c, rh, pres_hpa


class CCS811:
    REG_STATUS     = 0x00
    REG_MEAS_MODE  = 0x01
    REG_ALG_RESULT = 0x02
    REG_ENV_DATA   = 0x05
    REG_APP_START  = 0xF4
    REG_SW_RESET   = 0xFF

    def __init__(self, i2c, addr=0x5B):
        self.i2c = i2c
        self.addr = addr
        # reset
        self.i2c.writeto_mem(self.addr, self.REG_SW_RESET, bytes([0x11, 0xE5, 0x72, 0x8A]))
        time.sleep_ms(100)

        st = self._r8(self.REG_STATUS)
        app_valid = (st & 0x10) != 0
        fw_mode   = (st & 0x80) != 0
        if (not fw_mode) and app_valid:
            self.i2c.writeto(self.addr, bytes([self.REG_APP_START]))
            time.sleep_ms(100)

        # 1s mode
        self._w8(self.REG_MEAS_MODE, 0x10)
        time.sleep_ms(20)

    def _r8(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def _rN(self, reg, n):
        return self.i2c.readfrom_mem(self.addr, reg, n)

    def _w8(self, reg, v):
        self.i2c.writeto_mem(self.addr, reg, bytes([v]))

    def ready(self):
        return (self._r8(self.REG_STATUS) & 0x08) != 0

    def read(self):
        d = self._rN(self.REG_ALG_RESULT, 8)
        eco2 = (d[0] << 8) | d[1]
        tvoc = (d[2] << 8) | d[3]
        status = d[4]
        err = d[5]
        return eco2, tvoc, status, err

    def set_env(self, temp_c, rh):
        hum = int(rh * 512)
        tmp = int((temp_c + 25) * 512)
        payload = bytes([(hum >> 8) & 0xFF, hum & 0xFF, (tmp >> 8) & 0xFF, tmp & 0xFF])
        self.i2c.writeto_mem(self.addr, self.REG_ENV_DATA, payload)

        