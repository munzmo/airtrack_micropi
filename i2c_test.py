from machine import Pin, I2C
import time

SDA = 21
SCL = 22

i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=50000)

def r8(addr, reg):
    return i2c.readfrom_mem(addr, reg, 1)[0]

addrs = i2c.scan()
print("I2C scan:", [hex(a) for a in addrs])

bme = 0x76 if 0x76 in addrs else (0x77 if 0x77 in addrs else None)
ccs = 0x5B if 0x5B in addrs else (0x5A if 0x5A in addrs else None)

if bme:
    print("BME280 @", hex(bme), "Chip-ID:", hex(r8(bme, 0xD0)), "expect 0x60")
else:
    print("BME280 not found (0x76/0x77)")

if ccs:
    print("CCS811 @", hex(ccs), "HW_ID:", hex(r8(ccs, 0x20)), "expect 0x81",
          "STATUS:", hex(r8(ccs, 0x00)), "ERR_ID:", hex(r8(ccs, 0xE0)))
else:
    print("CCS811 not found (0x5A/0x5B)")
