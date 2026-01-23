import time

def wifi_and_ntp():
    try:
        import network
        import ntptime
        import secrets

        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        if not wlan.isconnected():
            wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PSK)
            for _ in range(75):  # ~15s
                if wlan.isconnected():
                    break
                time.sleep(0.2)

        if wlan.isconnected():
            try:
                ntptime.host = getattr(secrets, "NTP_HOST", "de.pool.ntp.org")
            except Exception:
                pass
            try:
                ntptime.settime()  # sets RTC (MicroPython epoch, but correct wall clock)
                print("boot: wifi ok, ntp ok")
            except Exception as e:
                print("boot: wifi ok, ntp failed:", e)
        else:
            print("boot: wifi not connected")

    except Exception as e:
        print("boot: skipped:", e)

wifi_and_ntp()
