"""
CCS811 real-time diagnostics for MicroPython (ESP32).
Served via GET /diag — provides full visibility into why the sensor
returns its current values and which factors influence the calculation.
"""

import json


def _status_decode(byte):
    """Decode CCS811 STATUS register into human-readable fields."""
    return {
        "fw_mode":    bool(byte & 0x80),  # True = application firmware running
        "app_valid":  bool(byte & 0x10),  # True = valid application loaded
        "data_ready": bool(byte & 0x08),  # True = new measurement available
        "error":      bool(byte & 0x01),  # True = error occurred, check error_id
        "raw":        byte,
    }


def _error_id_decode(byte):
    """Decode CCS811 ERROR_ID register into human-readable error flags."""
    return {
        "heater_supply":    bool(byte & 0x20),  # heater voltage not applied correctly
        "heater_fault":     bool(byte & 0x10),  # heater current out of range
        "max_resistance":   bool(byte & 0x08),  # sensor resistance at maximum range
        "measmode_invalid": bool(byte & 0x04),  # invalid measurement mode requested
        "read_reg_invalid": bool(byte & 0x02),  # invalid register read attempted
        "msg_invalid":      bool(byte & 0x01),  # invalid I2C message
        "raw":              byte,
    }


def build_diag(ctx):
    """
    Build a JSON diagnostics response for the CCS811 sensor.

    ctx keys:
        gas             CCS811 driver instance (wpse342.CCS811)
        latest          current measurement dict from main.py
        t_smooth        smoothed temperature last sent to set_env (°C)
        rh_smooth       smoothed humidity last sent to set_env (%)
        env_t_buf       current temperature smoothing buffer (list)
        env_rh_buf      current humidity smoothing buffer (list)
        eco2_min_seen   lowest eco2 in current 24h window (ppm), or None
        baseline_at_min baseline captured at eco2 minimum, or None
        baseline_file   path to baseline JSON file on flash
    """
    gas     = ctx["gas"]
    latest  = ctx["latest"]

    # Baseline saved on flash
    bl_saved = None
    try:
        with open(ctx["baseline_file"], "r") as f:
            bl_saved = json.load(f).get("bl")
    except Exception:
        pass

    # Current chip baseline
    bl_current = None
    try:
        bl_current = gas.get_baseline()
    except Exception:
        pass

    # Smoothing buffer state
    t_buf  = ctx.get("env_t_buf", [])
    rh_buf = ctx.get("env_rh_buf", [])

    # Status and error decoding (cached from last read())
    status_byte = getattr(gas, "_diag_status", None)
    err_id_byte = getattr(gas, "_diag_err_id", None)

    out = {
        # Current sensor output
        "readings": {
            "eco2_ppm": latest.get("eco2"),
            "tvoc_ppb": latest.get("tvoc"),
        },

        # Environmental compensation: what was measured vs. what was sent to chip
        "env_compensation": {
            "t_raw_c":      latest.get("t"),
            "rh_raw_pct":   latest.get("rh"),
            "t_smooth_c":   ctx.get("t_smooth"),
            "rh_smooth_pct": ctx.get("rh_smooth"),
            "buffer_n":     len(t_buf),
            "t_buf":        [round(v, 2) for v in t_buf],
            "rh_buf":       [round(v, 2) for v in rh_buf],
        },

        # Baseline state: chip value, saved value, current 24h window tracking
        "baseline": {
            "current_chip":    bl_current,
            "saved_disk":      bl_saved,
            "eco2_min_window": ctx.get("eco2_min_seen"),
            "baseline_at_min": ctx.get("baseline_at_min"),
        },

        # Raw MOX sensor data: heater current and ADC resistance reading
        # Higher ADC = higher sensor resistance = cleaner air
        "raw_sensor": {
            "current_ua": getattr(gas, "_diag_current_ua", None),
            "adc_raw":    getattr(gas, "_diag_adc_raw", None),
        },

        # CCS811 STATUS register decoded
        "status": _status_decode(status_byte) if status_byte is not None else None,

        # CCS811 ERROR_ID register decoded (only relevant if status.error = true)
        "error_id": _error_id_decode(err_id_byte) if err_id_byte is not None else None,
    }

    return json.dumps(out) + "\n"
