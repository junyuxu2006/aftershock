#!/usr/bin/env python3
"""
model2.py - Edge Machine Learning Fragility Evaluator for Arduino Uno Q
======================================================================
Loads model2_rf.json and runs multi-tree ensemble inference:
  1. Ingests simulated ground motion physics (PGA, Arias, CAV, Duration, Soil, Age).
  2. Aggregates leaf probabilities across all 10 trees in model2_rf.json.
  3. Uses safety-biased probability thresholds to determine risk tier.
  4. Triggers RGB LED via the STM32 bridge only when Model 2 is active.
  5. POSTs the computed decision back to the Flask relay for 3D twin lockdown.
"""

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from arduino.router_bridge import Bridge

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(SCRIPT_DIR, "model2_rf.json"))
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://10.244.58.131:5000/api/telemetry")
MODE_URL = os.getenv("MODE_URL", "http://127.0.0.1:5000/api/mode")

led_queue = queue.Queue(maxsize=1)
bridge = None
last_led_risk = None
rf_model = None


def is_model2_active() -> bool:
  """Returns True only when the dashboard selector is set to Model 2."""
  try:
    req = urllib.request.Request(
        MODE_URL, headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=0.15) as resp:
      data = json.loads(resp.read().decode("utf-8"))
      return data.get("mode") == "model2"
  except Exception:
    return True


def load_model(filepath: str) -> dict:
  with open(filepath, "r") as f:
    model = json.load(f)
  print(
      f"[MODEL LOADED] {len(model['trees'])} Trees | Features:"
      f" {model['meta']['features']}"
  )
  return model


def predict_proba_json(model: dict, x: list) -> list:
  """Traverses decision trees to compute ensemble class probabilities."""
  tot = [0.0] * len(model["classes"])
  for t in model["trees"]:
    n = 0
    while t["children_left"][n] != -1:
      feat_idx = t["feature"][n]
      thresh = t["threshold"][n]
      n = t["children_left"][n] if x[feat_idx] <= thresh else t["children_right"][n]
    v = t["value"][n][0]
    s = sum(v)
    for i, c in enumerate(v):
      tot[i] += c / s
  n_trees = len(model["trees"])
  return [p / n_trees for p in tot]


def decide(model: dict, x: list, p_high=0.35, p_med=0.40, p_low=0.50):
  """Safety-biased decision mapping probabilities to threat tiers."""
  noise_floor = model.get("meta", {}).get("noise_floor_g", 0.03)
  if x[0] < noise_floor:
    return (
        "BASELINE",
        1.0,
        {"BASELINE": 1.0, "LOW": 0.0, "MEDIUM": 0.0, "HIGH": 0.0},
    )

  probs = predict_proba_json(model, x)
  pr = dict(zip(model["classes"], probs))
  pH = pr.get("HIGH", 0.0)
  pM = pr.get("MEDIUM", 0.0)
  pL = pr.get("LOW", 0.0)

  if pH >= p_high:
    tier = "HIGH"
    conf = pH
  elif pH + pM >= p_med:
    tier = "MEDIUM"
    conf = pH + pM
  elif pH + pM + pL >= p_low:
    tier = "LOW"
    conf = pH + pM + pL
  else:
    tier = "BASELINE"
    conf = pr.get("BASELINE", 0.0)

  return tier, conf, pr


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
      print(f"Error calling LED RPC: {error}")
    finally:
      led_queue.task_done()


def evaluate_model2_features(packet: dict) -> str:
  global rf_model

  # Reject packets missing explicit PGA to avoid reading Model 1 physical vibration
  if "pga" not in packet and packet.get("mode") != "model2_simulation_in_the_loop":
    return "BASELINE"

  pga = float(packet.get("pga", 0.0))
  arias = float(packet.get("arias", 0.0))
  sig_dur = float(packet.get("sig_dur", 10.0))
  cav = float(packet.get("cav", 0.0))
  soil = float(packet.get("soil_factor", 1.4))
  infra_age = float(packet.get("infra_age", 35.0))

  x = [pga, arias, sig_dur, cav, soil, infra_age]

  t0 = time.perf_counter()
  risk, conf, pr = decide(rf_model, x)
  dt_ms = (time.perf_counter() - t0) * 1000.0

  # Only change physical RGB LED if Model 2 is the active selection
  if is_model2_active():
    set_magnitude_led(risk)

  print(f"\n[MODEL 2 RF]: {risk} (Score: {conf*100:.1f}%) in {dt_ms:.2f} ms")

  response_payload = {
      "source": "uno_q_hardware",
      "mode": "uno_q_decision",
      "magnitude": risk,
      "computed_risk": risk,
      "confidence": round(conf, 3),
      "acceleration": pga,
      "event": risk in ("MEDIUM", "HIGH"),
      "status": f"Uno Q ML Decision: {risk} ({conf*100:.0f}%)",
      "timestamp": time.time(),
  }

  try:
    data_bytes = json.dumps(response_payload).encode("utf-8")
    post_req = urllib.request.Request(
        DASHBOARD_URL,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(post_req, timeout=0.5) as resp:
      pass
  except Exception as err:
    print(f"Failed to post decision to relay: {err}")

  return risk


def listen_for_simulation_events():
  global bridge, rf_model

  rf_model = load_model(MODEL_PATH)

  bridge = Bridge()
  bridge.connect()
  led_thread = threading.Thread(target=led_worker, daemon=True)
  led_thread.start()

  print("=" * 65)
  print(" Aftershock Model 2: Edge Random Forest Inference Engine")
  print(f" Polling Relay at: {DASHBOARD_URL}")
  print("=" * 65)

  last_seen_timestamp = 0

  try:
    while True:
      try:
        req = urllib.request.Request(
            DASHBOARD_URL, headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=0.5) as resp:
          data = json.loads(resp.read().decode("utf-8"))
          samples = data.get("samples", [])
          if samples:
            latest = samples[-1]
            ts = latest.get("timestamp", latest.get("server_timestamp", 0))
            source = latest.get("source", "")
            mode = latest.get("mode", "")

            is_own_post = (
                source == "uno_q_hardware" or mode == "uno_q_decision"
            )
            is_model1_post = source == "model1"
            is_sim_event = mode == "model2_simulation_in_the_loop" or (
                source == "sim" and "pga" in latest and "arias" in latest
            )

            # Execute only once per unique simulation packet
            if (
                ts > last_seen_timestamp
                and not is_own_post
                and not is_model1_post
                and is_sim_event
            ):
              last_seen_timestamp = ts
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
    print("\nStopping ML Evaluator...")
