#!/usr/bin/env python3
"""
model1.py - Model 1: Physical Demonstration for Arduino Uno Q
=============================================================
Runs on the Arduino Uno Q to process physical desk/shake table motions:
  - Reads physical Dual-MPU6050 accelerometers over I2C at 50 Hz
  - Computes sliding 50-sample Cosine Waveform Embedding & RMS energy
  - Classifies motion into HIGH, MEDIUM, or LOW risk directly on the Uno Q chip
  - Sends real-time telemetry back to the dashboard
  - Pushes real-time telemetry back to laptop relay (http://127.0.0.1:5000/api/telemetry)

Wiring Guide:
  Dual MPU6050:
    - Sensor 1: I2C addr 0x68 (SDA -> A4, SCL -> A5)
    - Sensor 2: I2C addr 0x69 (AD0 pulled HIGH to 3.3V)
  Single 4-Pin Common Cathode RGB LED:
    - Longest Pin (Cathode) -> GND (via 220-330 ohm resistor)
    - Red Leg   -> Pin 9  (PWM)
    - Green Leg -> Pin 10 (PWM)
    - Blue Leg  -> Pin 11 (PWM)

Run:
    python3 model1.py
"""

import os
import time
import math
import json
import queue
import threading
import urllib.request
import urllib.error
from collections import deque
import numpy as np
from arduino.router_bridge import Bridge

# Endpoint Configuration
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:5000/api/telemetry")
telemetry_queue = queue.Queue(maxsize=100)
led_queue = queue.Queue(maxsize=1)

# Sampling Configuration
FREQUENCY_HZ = 50
WINDOW_SAMPLES = 50   # 1.0 second sliding window (50 samples at 50 Hz)
STRIDE_SAMPLES = 5    # Evaluate vector embedding every 5 samples (10 Hz inference)

# Alert & Threshold Limits (in g, 1g = 9.80665 m/s^2)
LOW_RMS_LIMIT = 0.08
MEDIUM_RMS_LIMIT = 0.22
LOW_PEAK_LIMIT = 0.05
MEDIUM_PEAK_LIMIT = 0.15
HIGH_PEAK_LIMIT = 0.35

buffer_mpu1 = deque(maxlen=WINDOW_SAMPLES)
buffer_mpu2 = deque(maxlen=WINDOW_SAMPLES)

bridge_instance = None
last_led_risk = None

def telemetry_sender_worker():
    """Background thread sending JSON telemetry to the laptop relay without blocking I2C."""
    while True:
        payload = telemetry_queue.get()
        if payload is None:
            break
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                DASHBOARD_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=0.35) as resp:
                pass
        except Exception:
            pass
        finally:
            telemetry_queue.task_done()


def set_magnitude_led(risk: str):
    global last_led_risk
    if risk == last_led_risk:
        return
    last_led_risk = risk
    try:
        led_queue.get_nowait()
        led_queue.task_done()
    except queue.Empty:
        pass
    try:
        led_queue.put_nowait(risk)
    except queue.Full:
        pass


def led_worker():
    while True:
        risk = led_queue.get()
        if risk is None:
            led_queue.task_done()
            return
        try:
            bridge_instance.call("set_magnitude_led", risk)
        except Exception as error:
            print(f"Error setting RGB LED: {error}")
        finally:
            led_queue.task_done()

def compute_cosine_similarity(window_data: np.ndarray) -> float:
    """Computes cosine similarity between acceleration window and canonical seismic impulse."""
    if len(window_data) < 10:
        return 0.10
    norm_w = np.linalg.norm(window_data)
    if norm_w < 1e-4:
        return 0.05
    # Synthesize template impulsive wave of same length
    t = np.linspace(0, np.pi * 2, len(window_data))
    template = np.sin(t * 3.0) * np.exp(-t)
    template_norm = np.linalg.norm(template)
    if template_norm < 1e-4:
        return 0.10
    cosine = float(np.dot(window_data, template) / (norm_w * template_norm))
    return max(0.0, min(1.0, abs(cosine)))

def evaluate_model1(peak_g: float, rms: float, cosine: float) -> str:
    """Classifies risk level from physical motion on Uno Q."""
    if peak_g >= HIGH_PEAK_LIMIT or rms >= MEDIUM_RMS_LIMIT or (peak_g >= 0.22 and cosine >= 0.70):
        return "HIGH"
    elif peak_g >= MEDIUM_PEAK_LIMIT or rms >= LOW_RMS_LIMIT or cosine >= 0.45:
        return "MEDIUM"
    elif peak_g >= LOW_PEAK_LIMIT:
        return "LOW"
    return "BASELINE"


def on_accel_sample(ax1, ay1, az1, ax2, ay2, az2):
    if len(buffer_mpu1) >= WINDOW_SAMPLES:
        buffer_mpu1.popleft()

    sensor1_magnitude_g = (
        math.sqrt(ax1 ** 2 + ay1 ** 2 + az1 ** 2) / 9.80665
    )
    buffer_mpu1.append(sensor1_magnitude_g - 1.0)


def main():
    global bridge_instance

    bridge_instance = Bridge()
    bridge_instance.connect()
    try:
        bridge_instance.unprovide("accel_sample")
    except Exception:
        pass
    bridge_instance.provide("accel_sample", on_accel_sample)

    print("=" * 65)
    print(" Aftershock Model 1: Physical Sensor ML Monitor (Uno Q)")
    print(f" Target Relay URL: {DASHBOARD_URL}")
    print("=" * 65)

    sender_thread = threading.Thread(target=telemetry_sender_worker, daemon=True)
    sender_thread.start()
    led_thread = threading.Thread(target=led_worker, daemon=True)
    led_thread.start()

    last_eval_time = 0

    try:
        while True:
            now = time.time()
            if len(buffer_mpu1) >= WINDOW_SAMPLES and (now - last_eval_time) >= 0.10:
                last_eval_time = now
                arr = np.array(buffer_mpu1)
                peak_g = float(np.max(np.abs(arr)))
                rms = float(np.sqrt(np.mean(arr ** 2)))
                cosine = compute_cosine_similarity(arr)

                risk = evaluate_model1(peak_g, rms, cosine)
                set_magnitude_led(risk)

                payload = {
                    "acceleration": round(peak_g, 4),
                    "rms": round(rms, 4),
                    "cosine": round(cosine, 2),
                    "magnitude": risk,
                    "event": risk != "BASELINE",
                    "threshold": HIGH_PEAK_LIMIT,
                    "source": "uno_q_model1",
                    "status": f"Uno Q Model 1: {risk} | Peak={peak_g:.3f}g | RMS={rms:.3f}"
                }
                try:
                    telemetry_queue.put_nowait(payload)
                except queue.Full:
                    pass

                if risk != "BASELINE":
                    print(f"-> [PHYSICAL SHAKE DETECTED] Risk={risk} | Peak={peak_g:.3f}g | RMS={rms:.3f}")

            time.sleep(1.0 / FREQUENCY_HZ)

    except KeyboardInterrupt:
        print("\nStopping Model 1 monitor...")
    finally:
        led_queue.put(None)
        led_thread.join(timeout=1.0)
        try:
            bridge_instance.unprovide("accel_sample")
        except Exception:
            pass
        bridge_instance.disconnect()

if __name__ == "__main__":
    main()