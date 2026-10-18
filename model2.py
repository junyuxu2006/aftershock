#!/usr/bin/env python3
"""
model2.py - Model 2: Simulation Ground Motion Ingestion for Arduino Uno Q
========================================================================
Runs on the Arduino Uno Q to provide Hardware Compute Authority:
  - The 3D Digital Twin streams realistic earthquake ground motion physics
    (PGA, Arias Intensity, Significant Duration, CAV, Soil Amplification, Age).
  - The Arduino Uno Q computes whether that event is HIGH, MEDIUM, or LOW risk.
  - The Uno Q returns the decision back to the laptop & 3D simulation!

Run:
    python3 model2.py
"""

import os
import time
import json
import urllib.request
import urllib.error
import queue
import threading
from arduino.router_bridge import Bridge

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://127.0.0.1:5000/api/telemetry")
led_queue = queue.Queue(maxsize=1)
bridge = None
last_led_risk = None


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
            bridge.call("set_magnitude_led", risk)
        except Exception as error:
            print(f"Error setting RGB LED: {error}")
        finally:
            led_queue.task_done()

def evaluate_model2_features(packet: dict) -> str:
    """
    Model 2 Inference Engine on Arduino Uno Q chip:
    Takes multi-parameter ground motion physics and determines risk level.
    """
    pga = float(packet.get("pga", packet.get("acceleration", 0.0)))
    arias = float(packet.get("arias", 0.0))
    sig_dur = float(packet.get("sig_dur", 10.0))
    cav = float(packet.get("cav", 0.0))
    soil = float(packet.get("soil_factor", 1.4))
    infra_age = float(packet.get("infra_age", 35.0))

    # Safety-biased decision logic matching building fragility curves
    if (pga >= 0.35 or arias >= 1.5 or (pga >= 0.22 and soil >= 1.6) or (cav >= 1.2 and infra_age >= 40.0)):
        risk = "HIGH"
    elif pga >= 0.12 or arias >= 0.45 or cav >= 0.40:
        risk = "MEDIUM"
    elif pga >= 0.04:
        risk = "LOW"
    else:
        risk = "BASELINE"

    set_magnitude_led(risk)
    print(f"\n[UNO Q MODEL 2 COMPUTED]: {risk}")
    print(f"  PGA: {pga:.3f}g | Arias: {arias:.2f} m/s | Dur: {sig_dur:.1f}s | Soil Factor: {soil:.2f}")

    return risk

def listen_for_simulation_events():
    global bridge

    bridge = Bridge()
    bridge.connect()
    led_thread = threading.Thread(target=led_worker, daemon=True)
    led_thread.start()

    """Polls relay or listens for simulation events to compute on Uno Q."""
    print("=" * 65)
    print(" Aftershock Model 2: Simulation Ground Motion Evaluator (Uno Q)")
    print(f" Listening for 3D Twin Physics at: {DASHBOARD_URL}")
    print(" Uno Q computes risk and dictates gate lockdowns to 3D city!")
    print("=" * 65)

    last_seen_timestamp = 0

    try:
        while True:
            try:
                req = urllib.request.Request(DASHBOARD_URL, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=0.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    samples = data.get("samples", [])
                    if samples:
                        latest = samples[-1]
                        ts = latest.get("server_timestamp", 0)
                        if ts > last_seen_timestamp:
                            last_seen_timestamp = ts
                            if latest.get("mode") == "model2_simulation_in_the_loop":
                                evaluate_model2_features(latest)
            except Exception:
                pass

            time.sleep(0.1)
    finally:
        led_queue.put(None)
        led_thread.join(timeout=1.0)
        bridge.disconnect()

if __name__ == "__main__":
    try:
        listen_for_simulation_events()
    except KeyboardInterrupt:
        print("\nStopping Model 2 evaluator...")