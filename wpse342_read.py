from machine import Pin, I2C
import time

SDA=21; SCL=22
i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=100000)

BME_ADDR = 0x77
CCS_ADDR = 0x5B

def r8(a, r):  return i2c.readfrom_mem(a, r, 1)[0]
def w8(a, r, v): i2c.writeto_mem(a, r, bytes([v]))
def rN(a, r, n): return i2c.readfrom_mem(a, r, n)
def s16(v): return v-65536 if v>32767 else v

# ---- BME280 calib ----
cal1 = rN(BME_ADDR, 0x88, 26)
dig_T1 = cal1[0] | (cal1[1]<<8)
dig_T2 = s16(cal1[2] | (cal1[3]<<8))
dig_T3 = s16(cal1[4] | (cal1[5]<<8))
dig_P1 = cal1[6] | (cal1[7]<<8)
dig_P2 = s16(cal1[8] | (cal1[9]<<8))
dig_P3 = s16(cal1[10] | (cal1[11]<<8))
dig_P4 = s16(cal1[12] | (cal1[13]<<8))
dig_P5 = s16(cal1[14] | (cal1[15]<<8))
dig_P6 = s16(cal1[16] | (cal1[17]<<8))
dig_P7 = s16(cal1[18] | (cal1[19]<<8))
dig_P8 = s16(cal1[20] | (cal1[21]<<8))
dig_P9 = s16(cal1[22] | (cal1[23]<<8))

dig_H1 = r8(BME_ADDR, 0xA1)
cal2 = rN(BME_ADDR, 0xE1, 7)
dig_H2 = s16(cal2[0] | (cal2[1]<<8))
dig_H3 = cal2[2]
e4, e5, e6 = cal2[3], cal2[4], cal2[5]
dig_H4 = s16((e4<<4) | (e5 & 0x0F))
dig_H5 = s16((e6<<4) | (e5 >> 4))
dig_H6 = cal2[6] if cal2[6] < 128 else cal2[6]-256

# ---- BME280 config ----
w8(BME_ADDR, 0xF2, 0x01)  # hum oversampling x1
w8(BME_ADDR, 0xF4, 0x27)  # temp/press x1, normal mode
w8(BME_ADDR, 0xF5, 0xA0)  # standby 1000ms
time.sleep_ms(20)

def bme_read():
    data = rN(BME_ADDR, 0xF7, 8)
    adc_p = (data[0]<<12) | (data[1]<<4) | (data[2]>>4)
    adc_t = (data[3]<<12) | (data[4]<<4) | (data[5]>>4)
    adc_h = (data[6]<<8)  | data[7]

    var1 = (((adc_t>>3) - (dig_T1<<1)) * dig_T2) >> 11
    var2 = (((((adc_t>>4) - dig_T1) * ((adc_t>>4) - dig_T1)) >> 12) * dig_T3) >> 14
    t_fine = var1 + var2
    temp_c = (((t_fine * 5 + 128) >> 8) / 100.0)

    var1 = t_fine - 128000
    var2 = var1*var1*dig_P6
    var2 = var2 + ((var1*dig_P5)<<17)
    var2 = var2 + (dig_P4<<35)
    var1 = ((var1*var1*dig_P3)>>8) + ((var1*dig_P2)<<12)
    var1 = (((1<<47)+var1) * dig_P1) >> 33
    if var1 == 0:
        pres_hpa = None
    else:
        p = 1048576 - adc_p
        p = (((p<<31) - var2) * 3125) // var1
        var1p = (dig_P9 * (p>>13) * (p>>13)) >> 25
        var2p = (dig_P8 * p) >> 19
        p = ((p + var1p + var2p) >> 8) + (dig_P7<<4)
        pres_hpa = (p/256.0)/100.0

    h = t_fine - 76800
    h = (((((adc_h<<14) - (dig_H4<<20) - (dig_H5*h)) + 16384) >> 15) *
         (((((((h*dig_H6) >> 10) * (((h*dig_H3) >> 11) + 32768)) >> 10) + 2097152) * dig_H2 + 8192) >> 14))
    h = h - (((((h>>15) * (h>>15)) >> 7) * dig_H1) >> 4)
    h = 0 if h < 0 else h
    h = 419430400 if h > 419430400 else h
    rh = ((h >> 12) / 1024.0)

    return temp_c, rh, pres_hpa

# ---- CCS811 config ----
REG_STATUS=0x00
REG_MEAS_MODE=0x01
REG_ALG_RESULT=0x02
REG_APP_START=0xF4
REG_SW_RESET=0xFF
REG_ENV_DATA=0x05

i2c.writeto_mem(CCS_ADDR, REG_SW_RESET, bytes([0x11,0xE5,0x72,0x8A]))
time.sleep_ms(100)
st = r8(CCS_ADDR, REG_STATUS)
app_valid = (st & 0x10) != 0
fw_mode  = (st & 0x80) != 0
if (not fw_mode) and app_valid:
    i2c.writeto(CCS_ADDR, bytes([REG_APP_START]))
    time.sleep_ms(100)

w8(CCS_ADDR, REG_MEAS_MODE, 0x10)  # 1s
time.sleep_ms(20)

def ccs_ready():
    return (r8(CCS_ADDR, REG_STATUS) & 0x08) != 0

def ccs_read():
    d = rN(CCS_ADDR, REG_ALG_RESULT, 8)
    return (d[0]<<8) | d[1], (d[2]<<8) | d[3], d[4], d[5]

def ccs_set_env(temp_c, rh):
    hum = int(rh * 512)
    tmp = int((temp_c + 25) * 512)
    payload = bytes([(hum>>8)&0xFF, hum&0xFF, (tmp>>8)&0xFF, tmp&0xFF])
    i2c.writeto_mem(CCS_ADDR, REG_ENV_DATA, payload)

print("json stream: one line per sample")
while True:
    t, rh, p = bme_read()
    ccs_set_env(t, rh)

    eco2 = None
    tvoc = None
    if ccs_ready():
        eco2, tvoc, status, err = ccs_read()

    # JSON w/o json-lib -> stable and fast
    p_s = "null" if p is None else ("%.2f" % p)
    eco2_s = "null" if eco2 is None else str(eco2)
    tvoc_s = "null" if tvoc is None else str(tvoc)

    print('{"t":%.2f,"rh":%.2f,"p":%s,"eco2":%s,"tvoc":%s}' %
          (t, rh, p_s, eco2_s, tvoc_s))

    time.sleep(2)
